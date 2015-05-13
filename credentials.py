#!/usr/bin/env python
import os
def get_creds():
    d = {}
    d['username'] = os.environ['OS_USERNAME']
    try:
        d['password'] = os.environ['OS_PASSWORD']
    except KeyError:
        d['password'] = raw_input('Enter your password:')
        print "OS_PASSWORD env variable is not set"
    d['auth_url'] = os.environ['OS_AUTH_URL']
    d['tenant_name'] = os.environ['OS_TENANT_NAME']
    d['region_name'] = os.environ['OS_REGION_NAME']
    return d

def get_keystone_creds():
    d = {}
    d['username'] = os.environ['OS_USERNAME']
    try:
        d['password'] = os.environ['OS_PASSWORD']
    except KeyError:
        print "OS_PASSWORD env variable is not set"
        d['password'] = raw_input('Enter your password:')
    d['auth_url'] = os.environ['OS_AUTH_URL']
    d['tenant_name'] = os.environ['OS_TENANT_NAME']
    d['region_name'] = os.environ['OS_REGION_NAME']
    return d

def get_nova_creds():
    d = {}
    d['username'] = os.environ['OS_USERNAME']
    try:
        d['api_key'] = os.environ['OS_PASSWORD']
    except KeyError:
        d['api_key'] = raw_input('Enter your password:')
        print "OS_PASSWORD env variable is not set"
    d['auth_url'] = os.environ['OS_AUTH_URL']
    d['project_id'] = os.environ['OS_TENANT_NAME']
    d['region_name'] = os.environ['OS_REGION_NAME']
    return d
