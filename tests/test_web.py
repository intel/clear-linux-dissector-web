# clear-dissector-web - tests for clear dissector web application setup
# by docker and docker compose
#
# Copyright (C) 2019 Intel Corporation
#
# Licensed under the MIT license, see COPYING.MIT for details
# NOTE: requires pytest-selenium plugin.
# Run : eg. pytest --driver Chrome
# Run : eg. pytest --driver Chrome --clr-url <custom_clear_app_url>
# where default clr-url=http://localhost:8080

import os
import subprocess
import pytest

basepath = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
username = 'testuser'
password = 'changeme1234!'

@pytest.fixture
def selenium_wait(selenium):
    selenium.implicitly_wait(2)
    return selenium

@pytest.fixture
def createtestuser():
    return subprocess.check_call(["docker-compose",
                                  "exec",
                                  "-T",
                                  "layersapp",
                                  "/opt/layerindex/manage.py",
                                  "loaddata",
                                  "testuser-data.json"],
                                  cwd=basepath)

@pytest.fixture
def resetaxes():
    return subprocess.check_call(["docker-compose",
                                  "exec",
                                  "-T",
                                  "layersapp",
                                  "/opt/layerindex/manage.py",
                                  "axes_reset"],
                                  cwd=basepath)

def check_testuser_data_removed(username):
    cmd = ''.join(
"""
from django.contrib.auth.models import User
import sys
users = User.objects.values('username')
for u in users:
    if '%s' in u['username']:
        sys.exit(1)
sys.exit(0)
""" % username)
    return subprocess.check_call(["docker-compose",
                                  "exec",
                                  "-T",
                                  "layersapp",
                                  "/opt/layerindex/manage.py",
                                  "shell",
                                  "-c",
                                  cmd],
                                 cwd=basepath)

def clr_login(selenium, url, login_account, login_password):
    selenium.get(url)
    selenium.find_element_by_id("id_username").send_keys(login_account)
    selenium.find_element_by_id("id_password").send_keys(login_password)
    selenium.find_element_by_css_selector('#login_form > input.btn.btn-default').click()
    return selenium

def clr_enter_image_comparison(selenium):
    selenium.find_element_by_css_selector('div.row:nth-child(4) > div:nth-child(1) > a:nth-child(1)').click()

def clr_find_image_comparison_header(selenium):
    return selenium.find_element_by_css_selector('body > div.header-bkgd > div > h2')

def clr_find_login_error_header(selenium):
    return selenium.find_element_by_css_selector('#login_form > ul > li')

def clr_delete_account(selenium, url, password):
    selenium.get(url)
    selenium.find_element_by_css_selector('#id_confirm_password').send_keys(password)
    selenium.find_element_by_css_selector('#content > form > input.btn.btn-danger').click()
    return selenium

def clr_find_account_deleted_header(selenium):
    return selenium.find_element_by_css_selector('#content > div')

def test_can_login_with_valid_account(selenium_wait, createtestuser, clr_url):
    selenium = clr_login(selenium_wait, '%s%s' % (clr_url, '/accounts/login/'), username, password)
    clr_enter_image_comparison(selenium)
    element = clr_find_image_comparison_header(selenium)
    assert element
    assert 'Compare Image' in element.text

def test_cannot_login_without_valid_account(selenium_wait, resetaxes, clr_url):
    selenium = clr_login(selenium_wait, '%s%s' % (clr_url, '/accounts/login/'), 'WRONG_user', 'WRONG_passwd')
    element = clr_find_login_error_header(selenium)
    assert element
    assert 'Please enter a correct username and password' in element.text

def test_can_remove_account_after_login(selenium_wait, createtestuser, clr_url):
    selenium = clr_login(selenium_wait, '%s%s' % (clr_url, '/accounts/login/'), username, password)
    clr_enter_image_comparison(selenium)
    element = clr_find_image_comparison_header(selenium)
    assert element
    assert 'Compare Image' in element.text
    selenium = clr_delete_account(selenium, '%s%s' % (clr_url, '/accounts/delete/'), password)
    element = clr_find_account_deleted_header(selenium)
    assert element
    assert 'Your user account has been successfully deleted' in element.text
    check_testuser_data_removed(username)
