# See README for how to use this.

FROM debian:stretch
LABEL maintainer="Michael Halstead <mhalstead@linuxfoundation.org>"

ENV PYTHONUNBUFFERED=1 \
    LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8 \
    LC_CTYPE=en_US.UTF-8
## Uncomment to set proxy ENVVARS within container
#ENV http_proxy http://your.proxy.server:port
#ENV https_proxy https://your.proxy.server:port
#ENV no_proxy localhost,127.0.0.0/8

# NOTE: we don't purge gcc below as we have some places in the OE metadata that look for it

COPY requirements.txt /
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
	autoconf \
	g++ \
	gcc \
	make \
	python-pip \
	python-mysqldb \
	python-dev \
	python-imaging \
	python3-pip \
	python3-mysqldb \
	python3-dev \
	python3-pil \
	libjpeg-dev \
	libmariadbclient-dev \
	locales \
	netcat-openbsd \
	curl \
	wget \
	git-core \
	vim \
	rpm2cpio \
	rpm \
	cpio \
	openssh-client \
    && echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen \
	&& locale-gen en_US.UTF-8 \
	&& update-locale \
    && wget https://dl.google.com/go/go1.13.3.linux-amd64.tar.gz \
    && tar xv -C /usr/local -f go*.tar.gz \
    && rm go*.tar.gz \
    && git clone https://github.com/intel/clear-linux-dissector \
    && cd clear-linux-dissector \
    && GOROOT=/usr/local/go PATH=/usr/local/go/bin:$PATH make \
    && GOROOT=/usr/local/go PATH=/usr/local/go/bin:$PATH make install DESTDIR=inst \
    && cp -a inst/usr/bin /opt/dissector \
    && cd .. \
    && rm -rf clear-linux-dissector \
    && rm -rf /usr/local/go \
    && pip3 install gunicorn \
    && pip install setuptools \
    && pip3 install setuptools \
    && pip install -r /requirements.txt \
    && pip3 install -r /requirements.txt \
    && apt-get purge -y autoconf g++ make python-dev python3-dev libjpeg-dev libmariadbclient-dev \
	&& apt-get autoremove -y \
	&& rm -rf /var/lib/apt/lists/* \
	&& apt-get clean

COPY . /opt/layerindex
RUN rm -rf /opt/layerindex/docker
COPY docker/settings.py /opt/layerindex/settings.py
COPY docker/refreshlayers.sh /opt/refreshlayers.sh
COPY docker/updatelayers.sh /opt/updatelayers.sh
COPY docker/migrate.sh /opt/migrate.sh
COPY docker/connectivity_check.sh /opt/connectivity_check.sh

RUN mkdir /opt/workdir \
	&& adduser --system --uid=500 layers \
	&& chown -R layers /opt/workdir \
	&& mkdir -p /home/layers/.ssh/ \
	&& chown layers:nogroup /home/layers/.ssh/
#COPY --chown=layers:nogroup docker/dotssh/* /home/layers/.ssh/
#RUN chmod 600 /home/layers/.ssh/*

USER layers

# Always copy in .gitconfig and proxy helper script (they need editing to be active)
COPY docker/.gitconfig /home/layers/.gitconfig
COPY docker/git-proxy /opt/bin/git-proxy

# Start Gunicorn
CMD ["/usr/local/bin/gunicorn", "wsgi:application", "--workers=4", "--bind=:5000", "--timeout=60", "--log-level=debug", "--chdir=/opt/layerindex"]
