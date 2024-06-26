#!/usr/bin/env python
# This file is part of tcollector.
# Copyright (C) 2013  The tcollector Authors.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.  This program is distributed in the hope that it
# will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty
# of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser
# General Public License for more details.  You should have received a copy
# of the GNU Lesser General Public License along with this program.  If not,
# see <http://www.gnu.org/licenses/>.
#
# Written by Mark Smith <mark@qq.is>.
#

"""A collector to gather statistics from a Riak node.

The following all have tags of 'type' which can be 'get' or 'put'.  Latency
is measured in fractional seconds.  All latency values are calculated over the
last 60 seconds and are moving values.

 - riak.vnode.requests
 - riak.node.requests
 - riak.node.latency.mean
 - riak.node.latency.median
 - riak.node.latency.95th
 - riak.node.latency.99th
 - riak.node.latency.100th

These metrics have no tags and are global:

 - riak.memory.total
 - riak.memory.allocated
 - riak.executing_mappers
 - riak.sys_process_count
 - riak.read_repairs
 - riak.connections
 - riak.connected_nodes
"""

import json
import os
import sys
import time
from urllib.request import urlopen

from collectors.etc import riak_conf
from collectors.lib import utils


CONFIG = riak_conf.get_default_config()

MAP = {
    'vnode_gets_total': ('vnode.requests', 'type=get'),
    'vnode_puts_total': ('vnode.requests', 'type=put'),
    'vnode_gets': ('vnode.requests.last.minute', 'type=get'),
    'vnode_puts': ('vnode.requests.last.minute', 'type=put'),
    'vnode_index_reads': ('vnode.indexing', 'type=read'),
    'vnode_index_writes': ('vnode.indexing', 'type=write'),
    'vnode_index_deletes': ('vnode.indexing', 'type=delete'),
    'vnode_index_writes_postings': ('vnode.index.posting', 'type=write'),
    'vnode_index_deletes_postings': ('vnode.index.posting', 'type=delete'),
    'node_gets_total': ('node.requests', 'type=get'),
    'node_puts_total': ('node.requests', 'type=put'),
    'node_gets': ('node.requests.last.minute', 'type=get'),
    'node_puts': ('node.requests.last.minute', 'type=put'),
    'node_get_fsm_active': ('node.active.fsm', 'type=get'),
    'node_put_fsm_active': ('node.active.fsm', 'type=put'),
    'node_get_fsm_time_mean': ('node.latency.mean', 'type=get'),
    'node_get_fsm_time_median': ('node.latency.median', 'type=get'),
    'node_get_fsm_time_95': ('node.latency.95th', 'type=get'),
    'node_get_fsm_time_99': ('node.latency.99th', 'type=get'),
    'node_get_fsm_time_100': ('node.latency.100th', 'type=get'),
    'node_put_fsm_time_mean': ('node.latency.mean', 'type=put'),
    'node_put_fsm_time_median': ('node.latency.median', 'type=put'),
    'node_put_fsm_time_95': ('node.latency.95th', 'type=put'),
    'node_put_fsm_time_99': ('node.latency.99th', 'type=put'),
    'node_put_fsm_time_100': ('node.latency.100th', 'type=put'),
    'node_get_fsm_rejected': ('node.rejected.fsm', 'type=get'),
    'node_put_fsm_rejected': ('node.rejected.fsm', 'type=put'),
    'node_get_fsm_siblings_mean': ('node.siblings.mean', ''),
    'node_get_fsm_siblings_median': ('node.siblings.median', ''),
    'node_get_fsm_siblings_95': ('node.siblings.95th', ''),
    'node_get_fsm_siblings_99': ('node.siblings.99th', ''),
    'node_get_fsm_siblings_100': ('node.siblings.100th', ''),
    'node_get_fsm_objsize_mean': ('node.object.size.mean', ''),
    'node_get_fsm_objsize_median': ('node.object.size.median', ''),
    'node_get_fsm_objsize_95': ('node.object.size.95th', ''),
    'node_get_fsm_objsize_99': ('node.object.size.99th', ''),
    'node_get_fsm_objsize_100': ('node.object.size.100th', ''),
    'pbc_connects_total': ('connections', ''),
    'pbc_active': ('pbc.active', ''),
    'read_repairs_total': ('read_repairs', ''),
    'sys_process_count': ('sys_process_count', ''),
    'executing_mappers': ('executing_mappers', ''),
    'mem_allocated': ('memory.allocated', ''),
    'mem_total': ('memory.total', ''),
    'memory_processes_used': ('memory.erlang', ''),
    'index_fsm_active': ('index.active.fsm', ''),
    'list_fsm_active': ('key.listing.active', ''),
    'cpu_nprocs': ('os.processes', '')
    #connected_nodes is calculated
}


def main():
    """Main loop"""

    # don't run if we're not a riak node
    if not os.path.exists("/usr/lib/riak"):
        return 13

    utils.drop_privileges()
    sys.stdin.close()

    interval = 15

    def print_stat(metric, value, tags=""):
        if value is not None:
            print("riak.%s %d %s %s" % (metric, ts, value, tags))

    while True:
        ts = int(time.time())

        req = urlopen(CONFIG['stats_endpoint'])
        if req is not None:
            obj = json.loads(req.read())
            for key in obj:
                if key not in MAP:
                    continue
                # this is a hack, but Riak reports latencies in microseconds.  they're fairly useless
                # to our human operators, so we're going to convert them to seconds.
                if 'latency' in MAP[key][0]:
                    obj[key] = obj[key] / 1000000.0
                print_stat(MAP[key][0], obj[key], MAP[key][1])
            if 'connected_nodes' in obj:
                print_stat('connected_nodes', len(obj['connected_nodes']), '')
        req.close()

        sys.stdout.flush()
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
