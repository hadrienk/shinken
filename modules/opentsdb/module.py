#!/usr/bin/python

# -*- coding: utf-8 -*-

# Copyright (C) 2009-2012:
#    Gabes Jean, naparuba@gmail.com
#    Gerhard Lausser, Gerhard.Lausser@consol.de
#    Gregory Starck, g.starck@gmail.com
#    Hartmut Goebel, h.goebel@goebel-consult.de
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Shinken is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Shinken.  If not, see <http://www.gnu.org/licenses/>.

"""This Class is a module for the Shinken Broker.
It sends the perfomance datas to OpenTSDB services.

The configuration contains a list of opentsdb servers. In case of loss of
connectivity, the modules tries the next value. If all fail, it will try
again later on.

When defining the host or service objects, certain tags (open tsdb tags) can
be added. 

By default, the module will add the host and the command that issued the 
perfomance data.

This class is heavily inspired by the tcollector from the OpenTSDB project
and graphite module. Big up.
"""

# TODO : Also buffering raw data, not only cPickle
# TODO : Better buffering like FIFO Buffer

import re
from socket import socket
import cPickle
import struct

from shinken.basemodule import BaseModule
from shinken.log import logger
from shinken.misc.perfdata import PerfDatas

properties = {
    'daemons': ['broker'],
    'type': 'opentsdb_perfdata',
    'external': False,
}


# Called by the plugin manager to get a broker
def get_instance(mod_conf):
    logger.info("[OpenTSDB broker] Get a openTSDB data module for plugin %s" % mod_conf.get_name())
    instance = OpenTSDB_broker(mod_conf)
    return instance

class ReaderQueue(Queue):
    """A Queue for the reader thread"""

    def nput(self, value):
        """A nonblocking put, that simply logs and discards the value when the
           queue is full, and returns false if we dropped."""
        try:
            self.put(value, False)
        except Full:
            LOG.error("DROPPED LINE: %s", value)
            return False
        return True

class SenderThread(threading.Thread):
    """The SenderThread is responsible for maintaining a connection
       to the TSD and sending the data we're getting over to it.  This
       thread is also responsible for doing any sort of emergency
       buffering we might need to do if we can't establish a connection
       and we need to spool to disk.  That isn't implemented yet."""

    def __init__(self, reader, dryrun, hosts, self_report_stats, tags):
        """Constructor.

        Args:
          reader: A reference to a ReaderThread instance.
          dryrun: If true, data points will be printed on stdout instead of
            being sent to the TSD.
          hosts: List of (host, port) tuples defining list of TSDs
          self_report_stats: If true, the reader thread will insert its own
            stats into the metrics reported to TSD, as if those metrics had
            been read from a collector.
          tags: A string containing tags to append at for every data point.
        """
        super(SenderThread, self).__init__()

        self.dryrun = dryrun
        self.reader = reader
        self.tagstr = tags
        self.hosts = hosts  # A list of (host, port) pairs.
        # Randomize hosts to help even out the load.
        random.shuffle(self.hosts)
        self.blacklisted_hosts = set()  # The 'bad' (host, port) pairs.
        self.current_tsd = -1  # Index in self.hosts where we're at.
        self.host = None  # The current TSD host we've selected.
        self.port = None  # The port of the current TSD.
        self.tsd = None   # The socket connected to the aforementioned TSD.
        self.last_verify = 0
        self.sendq = []
        self.self_report_stats = self_report_stats

    def pick_connection(self):
        """Picks up a random host/port connection."""
        # Try to get the next host from the list, until we find a host that
        # isn't in the blacklist, or until we run out of hosts (i.e. they
        # are all blacklisted, which typically happens when we lost our
        # connectivity to the outside world).
        for self.current_tsd in xrange(self.current_tsd + 1, len(self.hosts)):
            hostport = self.hosts[self.current_tsd]
            if hostport not in self.blacklisted_hosts:
                break
        else:
            LOG.info('No more healthy hosts, retry with previously blacklisted')
            random.shuffle(self.hosts)
            self.blacklisted_hosts.clear()
            self.current_tsd = 0
            hostport = self.hosts[self.current_tsd]

        self.host, self.port = hostport
        LOG.info('Selected connection: %s:%d', self.host, self.port)

    def blacklist_connection(self):
        """Marks the current TSD host we're trying to use as blacklisted.

           Blacklisted hosts will get another chance to be elected once there
           will be no more healthy hosts."""
        # FIXME: Enhance this naive strategy.
        LOG.info('Blacklisting %s:%s for a while', self.host, self.port)
        self.blacklisted_hosts.add((self.host, self.port))

    def run(self):
        """Main loop.  A simple scheduler.  Loop waiting for 5
           seconds for data on the queue.  If there's no data, just
           loop and make sure our connection is still open.  If there
           is data, wait 5 more seconds and grab all of the pending data and
           send it.  A little better than sending every line as its
           own packet."""

        errors = 0  # How many uncaught exceptions in a row we got.
        while ALIVE:
            try:
                self.maintain_conn()
                try:
                    line = self.reader.readerq.get(True, 5)
                except Empty:
                    continue
                self.sendq.append(line)
                time.sleep(5)  # Wait for more data
                while True:
                    # prevents self.sendq fast growing in case of sending fails
                    # in send_data()
                    if len(self.sendq) > MAX_SENDQ_SIZE:
                        break
                    try:
                        line = self.reader.readerq.get(False)
                    except Empty:
                        break
                    self.sendq.append(line)

                self.send_data()
                errors = 0  # We managed to do a successful iteration.
            except (ArithmeticError, EOFError, EnvironmentError, LookupError,
                    ValueError), e:
                errors += 1
                if errors > MAX_UNCAUGHT_EXCEPTIONS:
                    shutdown()
                    raise
                LOG.exception('Uncaught exception in SenderThread, ignoring')
                time.sleep(1)
                continue
            except:
                LOG.exception('Uncaught exception in SenderThread, going to exit')
                shutdown()
                raise

    def verify_conn(self):
        """Periodically verify that our connection to the TSD is OK
           and that the TSD is alive/working."""
        if self.tsd is None:
            return False

        # if the last verification was less than a minute ago, don't re-verify
        if self.last_verify > time.time() - 60:
            return True

        # we use the version command as it is very low effort for the TSD
        # to respond
        LOG.debug('verifying our TSD connection is alive')
        try:
            self.tsd.sendall('version\n')
        except socket.error, msg:
            self.tsd = None
            self.blacklist_connection()
            return False

        bufsize = 4096
        while ALIVE:
            # try to read as much data as we can.  at some point this is going
            # to block, but we have set the timeout low when we made the
            # connection
            try:
                buf = self.tsd.recv(bufsize)
            except socket.error, msg:
                self.tsd = None
                self.blacklist_connection()
                return False

            # If we don't get a response to the `version' request, the TSD
            # must be dead or overloaded.
            if not buf:
                self.tsd = None
                self.blacklist_connection()
                return False

            # Woah, the TSD has a lot of things to tell us...  Let's make
            # sure we read everything it sent us by looping once more.
            if len(buf) == bufsize:
                continue

            # If everything is good, send out our meta stats.  This
            # helps to see what is going on with the tcollector.
            if self.self_report_stats:
                strs = [
                        ('reader.lines_collected',
                         '', self.reader.lines_collected),
                        ('reader.lines_dropped',
                         '', self.reader.lines_dropped)
                       ]

                for col in all_living_collectors():
                    strs.append(('collector.lines_sent', 'collector='
                                 + col.name, col.lines_sent))
                    strs.append(('collector.lines_received', 'collector='
                                 + col.name, col.lines_received))
                    strs.append(('collector.lines_invalid', 'collector='
                                 + col.name, col.lines_invalid))

                ts = int(time.time())
                strout = ["tcollector.%s %d %d %s"
                          % (x[0], ts, x[2], x[1]) for x in strs]
                for string in strout:
                    self.sendq.append(string)

            break  # TSD is alive.

        # if we get here, we assume the connection is good
        self.last_verify = time.time()
        return True

    def maintain_conn(self):
        """Safely connect to the TSD and ensure that it's up and
           running and that we're not talking to a ghost connection
           (no response)."""

        # dry runs are always good
        if self.dryrun:
            return

        # connection didn't verify, so create a new one.  we might be in
        # this method for a long time while we sort this out.
        try_delay = 1
        while ALIVE:
            if self.verify_conn():
                return

            # increase the try delay by some amount and some random value,
            # in case the TSD is down for a while.  delay at most
            # approximately 10 minutes.
            try_delay *= 1 + random.random()
            if try_delay > 600:
                try_delay *= 0.5
            LOG.debug('SenderThread blocking %0.2f seconds', try_delay)
            time.sleep(try_delay)

            # Now actually try the connection.
            self.pick_connection()
            try:
                addresses = socket.getaddrinfo(self.host, self.port, socket.AF_UNSPEC,
                                               socket.SOCK_STREAM, 0)
            except socket.gaierror, e:
                if e[0] in (socket.EAI_AGAIN, socket.EAI_NONAME):
                    continue
                raise
            for family, socktype, proto, canonname, sockaddr in addresses:
                try:
                    self.tsd = socket.socket(family, socktype, proto)
                    self.tsd.settimeout(15)
                    self.tsd.connect(sockaddr)
                    # if we get here it connected
                    break
                except socket.error, msg:
                    LOG.warning('Connection attempt failed to %s:%d: %s',
                                self.host, self.port, msg)
                self.tsd.close()
                self.tsd = None
            if not self.tsd:
                LOG.error('Failed to connect to %s:%d', self.host, self.port)
                self.blacklist_connection()

    def send_data(self):
        """Sends outstanding data in self.sendq to the TSD in one operation."""

        # construct the output string
        out = ''

        # in case of logging we use less efficient variant
        if LOG.level == logging.DEBUG:
            for line in self.sendq:
                line = "put %s%s" % (line, self.tagstr)
                out += line + '\n'
                LOG.debug('SENDING: %s', line)
        else:
            out = "".join("put %s%s\n" % (line, self.tagstr) for line in self.sendq)

        if not out:
            LOG.debug('send_data no data?')
            return

        # try sending our data.  if an exception occurs, just error and
        # try sending again next time.
        try:
            if self.dryrun:
                print out
            else:
                self.tsd.sendall(out)
            self.sendq = []
        except socket.error, msg:
            LOG.error('failed to send data: %s', msg)
            try:
                self.tsd.close()
            except socket.error:
                pass
            self.tsd = None
            self.blacklist_connection()

        # FIXME: we should be reading the result at some point to drain
        # the packets out of the kernel's queues


# Class for the OpenTSDB Broker
class OpenTSDB_broker(BaseModule):

    def __init__(self, modconf):
        """
        Initi
        """	
        BaseModule.__init__(self, modconf)

        self.host = getattr(modconf, 'host', 'localhost')
        self.port = int(getattr(modconf, 'port', '2003'))

        self.use_pickle = getattr(modconf, 'use_pickle', '0') == '1'
        if self.use_pickle:
            self.port = int(getattr(modconf, 'port', '2004'))
        else:
            self.port = int(getattr(modconf, 'port', '2003'))

        self.tick_limit = int(getattr(modconf, 'tick_limit', '300'))
        self.buffer = []
        self.ticks = 0
        self.host_dict = {}
        self.svc_dict = {}
        self.multival = re.compile(r'_(\d+)$')

        # optional "sub-folder" in graphite to hold the data of a specific host
        self.graphite_data_source = \
            self.illegal_char.sub('_', getattr(modconf, 'graphite_data_source', ''))


    # Called by Broker so we can do init stuff
    # TODO: add conf param to get pass with init
    # Conf from arbiter!
    def init(self):
        logger.info("[OpenTSDB broker] I init the %s server connection to %s:%d" %
                    (self.get_name(), str(self.host), self.port))
        try:
            self.con = socket()
            self.con.connect((self.host, self.port))
        except IOError, err:
                logger.error("[Graphite broker] Graphite Carbon instance network socket!"
                             " IOError:%s" % str(err))
                raise
        logger.info("[Graphite broker] Connection successful to  %s:%d"
                    % (str(self.host), self.port))

    # Sending data to Carbon. In case of failure, try to reconnect and send again.
    # If carbon instance is down, data are buffered.
    def send_packet(self, p):
        try:
            self.con.sendall(p)
        except IOError:
            logger.error("[Graphite broker] Failed sending data to the Graphite Carbon instance !"
                         " Trying to reconnect ... ")
            try:
                self.init()
                self.con.sendall(p)
            except IOError:
                raise

    # For a perf_data like /=30MB;4899;4568;1234;0  /var=50MB;4899;4568;1234;0 /toto=
    # return ('/', '30'), ('/var', '50')
    def get_metric_and_value(self, perf_data):
        res = []
        metrics = PerfDatas(perf_data)

        for e in metrics:
            try:
                logger.debug("[Graphite broker] Groking: %s" % str(e))
            except UnicodeEncodeError:
                pass

            name = self.illegal_char.sub('_', e.name)
            name = self.multival.sub(r'.\1', name)

            # get metric value and its thresholds values if they exist
            name_value = {name: e.value}
            if e.warning and e.critical:
                name_value[name + '_warn'] = e.warning
                name_value[name + '_crit'] = e.critical
            # bailout if need
            if name_value[name] == '':
                continue

            try:
                logger.debug("[Graphite broker] End of grok: %s, %s" % (name, str(e.value)))
            except UnicodeEncodeError:
                pass
            for key, value in name_value.items():
                res.append((key, value))
        return res


    # Prepare service custom vars
    def manage_initial_service_status_brok(self, b):
        if '_GRAPHITE_POST' in b.data['customs']:
            self.svc_dict[(b.data['host_name'], b.data['service_description'])] = b.data['customs']


    # Prepare host custom vars
    def manage_initial_host_status_brok(self, b):
        if '_GRAPHITE_PRE' in b.data['customs']:
            self.host_dict[b.data['host_name']] = b.data['customs']


    # A service check result brok has just arrived, we UPDATE data info with this
    def manage_service_check_result_brok(self, b):
        data = b.data

        perf_data = data['perf_data']
        couples = self.get_metric_and_value(perf_data)

        # If no values, we can exit now
        if len(couples) == 0:
            return

        hname = self.illegal_char.sub('_', data['host_name'])
        if data['host_name'] in self.host_dict:
            customs_datas = self.host_dict[data['host_name']]
            if '_GRAPHITE_PRE' in customs_datas:
                hname = ".".join((customs_datas['_GRAPHITE_PRE'], hname))

        desc = self.illegal_char.sub('_', data['service_description'])
        if (data['host_name'], data['service_description']) in self.svc_dict:
            customs_datas = self.svc_dict[(data['host_name'], data['service_description'])]
            if '_GRAPHITE_POST' in customs_datas:
                desc = ".".join((desc, customs_datas['_GRAPHITE_POST']))

        check_time = int(data['last_chk'])

        try:
            logger.debug("[Graphite broker] Hostname: %s, Desc: %s, check time: %d, perfdata: %s"
                         % (hname, desc, check_time, str(perf_data)))
        except UnicodeEncodeError:
            pass

        if self.graphite_data_source:
            path = '.'.join((hname, self.graphite_data_source, desc))
        else:
            path = '.'.join((hname, desc))

        if self.use_pickle:
            # Buffer the performance data lines
            for (metric, value) in couples:
                self.buffer.append(("%s.%s" % (path, metric),
                                   ("%d" % check_time, "%s" % str(value))))

        else:
            lines = []
            # Send a bulk of all metrics at once
            for (metric, value) in couples:
                lines.append("%s.%s %s %d" % (path, metric, str(value), check_time))
            packet = '\n'.join(lines) + '\n'  # Be sure we put \n every where
            try:
                logger.debug("[Graphite broker] Launching: %s" % packet)
            except UnicodeEncodeError:
                pass
            try:
                self.send_packet(packet)
            except IOError:
                logger.error("[Graphite broker] Failed sending to the Graphite Carbon."
                             " Data are lost")


    # A host check result brok has just arrived, we UPDATE data info with this
    def manage_host_check_result_brok(self, b):
        data = b.data

        perf_data = data['perf_data']
        couples = self.get_metric_and_value(perf_data)

        # If no values, we can exit now
        if len(couples) == 0:
            return

        hname = self.illegal_char.sub('_', data['host_name'])
        if data['host_name'] in self.host_dict:
            customs_datas = self.host_dict[data['host_name']]
            if '_GRAPHITE_PRE' in customs_datas:
                hname = ".".join((customs_datas['_GRAPHITE_PRE'], hname))

        check_time = int(data['last_chk'])

        try:
            logger.debug("[Graphite broker] Hostname %s, check time: %d, perfdata: %s"
                         % (hname, check_time, str(perf_data)))
        except UnicodeEncodeError:
            pass

        if self.graphite_data_source:
            path = '.'.join((hname, self.graphite_data_source))
        else:
            path = hname

        if self.use_pickle:
            # Buffer the performance data lines
            for (metric, value) in couples:
                if value:
                    self.buffer.append(("%s.__HOST__.%s" % (path, metric),
                                       ("%d" % check_time,
                                        "%s" % value)))
        else:
            lines = []
            # Send a bulk of all metrics at once
            for (metric, value) in couples:
                if value:
                    lines.append("%s.__HOST__.%s %s %d" % (path, metric,
                                                           value, check_time))
            packet = '\n'.join(lines) + '\n'  # Be sure we put \n every where
            try:
                logger.debug("[Graphite broker] Launching: %s" % packet)
            except UnicodeEncodeError:
                pass
            try:
                self.send_packet(packet)
            except IOError:
                logger.error("[Graphite broker] Failed sending to the Graphite Carbon."
                             " Data are lost")


    def hook_tick(self, brok):
        """Each second the broker calls the hook_tick function
           Every tick try to flush the buffer
        """
        if self.use_pickle:
            if self.ticks >= self.tick_limit:
                # If the number of ticks where data was not
                # sent successfully to Graphite reaches the bufferlimit.
                # Reset the buffer and reset the ticks
                logger.error("[Graphite broker] Buffering time exceeded. Freeing buffer")
                self.buffer = []
                self.ticks = 0
                return

            # Format the data
            payload = cPickle.dumps(self.buffer)
            header = struct.pack("!L", len(payload))
            packet = header + payload

            try:
                self.send_packet(packet)
                # Flush the buffer after a successful send to Graphite
                self.buffer = []
                self.ticks = 0
            except IOError:
                self.ticks += 1
                logger.error("[Graphite broker] Sending data Failed. Buffering state : %s / %s"
                             % (self.ticks, self.tick_limits))
