#! /usr/bin/env python
# Copyright 2013 AT&T Services, Inc.
#           2015 Catalyst IT Ltd.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import argparse
from credentials import get_nova_creds
import json
import logging
from logging.handlers import SysLogHandler
from novaclient.v1_1 import client
import os
import pprint
import time
LOG = logging.getLogger("livemigrate_instances")
LOG_FORMAT = '%(asctime)s %(name)-12s %(levelname)-8s %(message)s'
LOG_DATE = '%m-%d %H:%M'
DESCRIPTION = "Live migration tool to clear out a hypervisor"


def parse_args():
    # ensure environment has necessary items to authenticate
    for key in ['OS_TENANT_NAME', 'OS_USERNAME', 'OS_PASSWORD',
                'OS_AUTH_URL', 'OS_REGION_NAME']:
        if key not in os.environ.keys():
            LOG.exception("Your environment is missing '%s'")
    ap = argparse.ArgumentParser(description=DESCRIPTION)
    ap.add_argument('-d', '--debug', action='store_true',
                    default=False, help='Show debugging output')
    ap.add_argument('-q', '--quiet', action='store_true', default=False,
                    help='Only show error and warning messages')
    ap.add_argument('-n', '--noop', action='store_true', default=False,
                    help='Do not do any modifying operations (dry-run)')
    ap.add_argument('-m', '--migrate', action='store_true', default=False,
                    help='Migrate from one host to another')
    ap.add_argument('-r', '--recover', action='store_true', default=False,
                    help='Move hosts previously migrated back home')
    ap.add_argument('--source',
                    help='the FQDN of a hypervisor to move instances \
                    away from')
    ap.add_argument('--dest',
                    help='the FQDN of a hypervisor to move instances \
                    to')
    ap.add_argument('--file', default='./results.json',
                    help='The file in which to store/retrieve the server list')
    ap.add_argument('--insecure', action='store_true', default=False,
                    help='Explicitly allow tool to perform '
                         '"insecure" SSL (https) requests. The server\'s '
                         'certificate will not be verified against any '
                         'certificate authorities. This option should be used '
                         'with caution.')
    return ap.parse_args()


def setup_logging(args):
    level = logging.INFO
    if args.quiet:
        level = logging.WARN
    if args.debug:
        level = logging.DEBUG
    logging.basicConfig(level=level, format=LOG_FORMAT, date_fmt=LOG_DATE)
    handler = SysLogHandler(address='/dev/log')
    syslog_formatter = logging.Formatter('%(name)s: %(levelname)s %(message)s')
    handler.setFormatter(syslog_formatter)
    LOG.addHandler(handler)


def get_hypervisor_instances(args, nova):
    instance_list = []
    # check if the hypervisor exists and is unique
    hypervisor_id = nova.hypervisors.search(args.source)
    if len(hypervisor_id) != 1:
        print("The hypervisor %s was either not found, or found more than \
              once" % args.source)
        raise SystemExit
    hyp_obj = nova.hypervisors.get(hypervisor_id[0])
    for instance in nova.servers.list(search_opts={'all_tenants': True}):
        inst_hyp = getattr(instance, 'OS-EXT-SRV-ATTR:hypervisor_hostname')
        if hyp_obj.hypervisor_hostname == inst_hyp:
            instance_list.append(instance)
    return instance_list


def changed_hypervisor(instance, orig_hypervisor):
    instance.get()
    current_hypervisor = getattr(instance,
                                 'OS-EXT-SRV-ATTR:hypervisor_hostname')
    if current_hypervisor == orig_hypervisor:
        return False
    else:
        # TODO(XP) add a check that the correct dest was used
        return current_hypervisor


def migrate_instance(args, nova, instance, dest, timeout):
    result = {}
    start_hypervisor = getattr(instance, 'OS-EXT-SRV-ATTR:hypervisor_hostname')
    message = "Migrating %s from %s" % (instance.id, start_hypervisor)
    print(message)
    if args.noop:
        result = {'instance': instance.id,
                  'state': instance.status,
                  'message': "Instance left alone",
                  'start_hypervisor': start_hypervisor,
                  'end_hypervisor': start_hypervisor}
        return result
    else:
        if instance.status == 'ACTIVE':
            instance.live_migrate(host=dest)
            check = True
        elif instance.status == 'SHUTOFF':
            instance.migrate()
            check = True
        else:
            check = False
    if check:
        wait_time = 0
        while wait_time < timeout:
            new_hypervisor = changed_hypervisor(instance, start_hypervisor)
            if new_hypervisor:
                # TODO(XP) this is all well and good, but if it fails it will
                # wait until the timeout rather than fail immediately
                result = {'instance': instance.id,
                          'state': instance.status,
                          'message': "Migrated OK",
                          'start_hypervisor': start_hypervisor,
                          'end_hypervisor': new_hypervisor}
                return result
            else:
                time.sleep(5)
                wait_time += 5
                print("wait time is now %s" % wait_time)

    result = {'instance': instance.id,
              'state': instance.status,
              'message': "Migration failed or timed out",
              'start_hypervisor': start_hypervisor,
              'end_hypervisor': start_hypervisor}
    print("Instance %s is now on %s, %s, status is %s" %
          (result['instance'],
           result['end_hypervisor'],
           result['message'],
           result['state']))
    return result


def migrate_away(args, nova, timeout):
    instances_to_migrate = get_hypervisor_instances(args, nova)
    dest_id = nova.hypervisors.search(args.dest)
    if len(dest_id) != 1:
        print("The hypervisor %s was either not found, or found more than \
              once" % args.source)
        raise SystemExit
    dest = nova.hypervisors.get(dest_id[0]).hypervisor_hostname
    final_results = []
    for instance in instances_to_migrate:
        hypervisor_hostname = getattr(instance,
                                      'OS-EXT-SRV-ATTR:hypervisor_hostname')
        result = migrate_instance(args, nova, instance, dest, timeout)
        final_results.append(result)
        # ugh, a magic sleep to let things settle down
        time.sleep(5)
    pprint.pprint(final_results)
    # TODO(XP) this needs exception handling
    with open(args.file, 'w') as fp:
        json.dump(final_results, fp)
    fp.close()


def recover(args, nova, timeout):
    # TODO(XP) this needs exception handling
    with open(args.file, 'r') as fp:
        temp_locations = json.load(fp)
    fp.close()

    final_results = []
    for entry in temp_locations:
        if entry['end_hypervisor'] == entry['start_hypervisor']:
            print("Instance %s left alone" % entry['instance'])
        else:
            # set up instance, dest list
            instance = nova.servers.get(entry['instance'])
            dest = entry['start_hypervisor']
            result = migrate_instance(args, nova, instance, dest, timeout)
        final_results.append(result)
        # ugh, a magic sleep to let things settle down
        time.sleep(5)
    pprint.pprint(final_results)


def main():
    args = parse_args()
    # setup_logging(args)
    try:
        nova = client.Client(**get_nova_creds())
    except Exception:
        raise
    timeout = 60
    if ((args.migrate and args.recover) or (args.migrate is False
                                            and args.recover is False)):
        print("Please either migrate, or recover, but not both")
    if args.migrate:
        if (not args.source) or (not args.dest):
            print("Must supply both source and destination hypervisors")
            raise SystemExit
        migrate_away(args, nova, timeout)

    if args.recover:
        recover(args, nova, timeout)


if __name__ == '__main__':
    main()
