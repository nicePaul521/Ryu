from __future__ import division
from ryu import cfg
import copy
from operator import attrgetter
from ryu.base import app_manager
from ryu.base.app_manager import lookup_service_brick
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.topology.switches import Switches
from ryu.topology.switches import LLDPPacket
import networkx as nx
import time
from ryu.lib.packet import packet
import setting

CONF = cfg.CONF

class QoS(app_manager.RyuApp):
    """
        Qos is a app collect delay,bandwidth and loss on links.

    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(QoS, self).__init__(*args, **kwargs)
        self.name = 'qos'
        self.datapaths = {}
        self.port_stats = {}
        self.port_speed = {}
        self.flow_stats = {}
        self.flow_speed = {}
        self.stats = {}
        self.port_features = {}
        self.free_bandwidth = {}
        self.echo_latency = {}
        self.link_loss = {}
        self.awareness = lookup_service_brick('awareness')
        self.sw_module = lookup_service_brick('switches')
        self.graph = None
        self._graph = None
        self.capabilities = None
        self.best_paths = None
        self.sending_echo_request_interval = 0.05
        self.identify = False
        # Start to green thread to monitor traffic and calculating
        # free bandwidth of links respectively.
        self.monitor_thread = hub.spawn(self._monitor)
        self.save_thread = hub.spawn(self._save_graph)

    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        """
            Record datapath's info
        """
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if not datapath.id in self.datapaths:
                self.logger.debug('register datapath: %016x', datapath.id)
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.debug('unregister datapath: %016x', datapath.id)
                del self.datapaths[datapath.id]

    def _monitor(self):
        """
            Main entry method of monitoring traffic.
        """
        # while CONF.weight == 'bw':
        while True:
            self._send_echo_request()
            self.create_link_delay()
            # self.get_loss()
            self.stats['flow'] = {}
            self.stats['port'] = {}
            for dp in self.datapaths.values():
                self.port_features.setdefault(dp.id, {})
                self.link_loss.setdefault(dp.id,{})
                self._request_stats(dp)
                # refresh data.
                self.capabilities = None
                self.best_paths = None
            hub.sleep(setting.MONITOR_PERIOD)
            self.show_stat()
    
    def _save_graph(self):
        """
            Save bandwidth data into networkx graph object.
        """
        # while CONF.weight == 'bw':
        while True:
            self.get_loss()
            self.graph = self.create_bw_graph(self.free_bandwidth)
            self.logger.debug("save_freebandwidth")
            hub.sleep(setting.MONITOR_PERIOD)

    def _send_echo_request(self):
        """
            Seng echo request msg to datapath.
        """
        for datapath in self.datapaths.values():
            parser = datapath.ofproto_parser
            echo_req = parser.OFPEchoRequest(datapath,
                                             data="%.12f" % time.time())
            datapath.send_msg(echo_req)
            # Important! Don't send echo request together, Because it will
            # generate a lot of echo reply almost in the same time.
            # which will generate a lot of delay of waiting in queue
            # when processing echo reply in echo_reply_handler.

            hub.sleep(self.sending_echo_request_interval)

    def _request_stats(self, datapath):
        """
            Sending request msg to datapath
        """
        self.logger.debug('send stats request: %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPPortDescStatsRequest(datapath, 0)
        datapath.send_msg(req)

        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)

        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

    def get_delay(self, src, dst):
        """
            Get link delay.
                        Controller
                        |        |
        src echo latency|        |dst echo latency
                        |        |
                   SwitchA-------SwitchB
                        
                    fwd_delay--->
                        <----reply_delay
            delay = (forward delay + reply delay - src datapath's echo latency
        """
        try:
            fwd_delay = self.awareness.graph[src][dst]['lldpdelay']
            re_delay = self.awareness.graph[dst][src]['lldpdelay']
            src_latency = self.echo_latency[src]
            dst_latency = self.echo_latency[dst]
            
            delay = (fwd_delay + re_delay - src_latency - dst_latency)/2
            return max(delay, 0)
        except:
            return float('inf')

    def _save_lldp_delay(self, src=0, dst=0, lldpdelay=0):
        try:
            self.awareness.graph[src][dst]['lldpdelay'] = lldpdelay
        except:
            if self.awareness is None:
                self.awareness = lookup_service_brick('awareness')
            return
    
    def create_link_delay(self):
        """
            Create link delay data, and save it into graph object.
        """
        try:
            for src in self.awareness.graph:
                for dst in self.awareness.graph[src]:
                    if src == dst:
                        self.awareness.graph[src][dst]['delay'] = 0
                        continue
                    delay = self.get_delay(src, dst)
                    delay = round(delay*10**3,4)
                    self.awareness.graph[src][dst]['delay'] = delay
        except:
            if self.awareness is None:
                self.awareness = lookup_service_brick('awareness')
            return

    def get_loss(self):
        try:
            graph = self.awareness.graph
            link_to_port = self.awareness.link_to_port
            for link in link_to_port:
                (src_dpid,dst_dpid) = link
                (src_port,dst_port) = link_to_port[link]
                flow_lst = [k for k in self.link_loss[src_dpid].keys() for j in self.link_loss[dst_dpid].keys() if k==j]
                if flow_lst:
                    tx_packets = self.link_loss[src_dpid][flow_lst[1]]
                    rx_packets = self.link_loss[dst_dpid][flow_lst[1]]
                    loss_ratio = abs((tx_packets-rx_packets)/max(tx_packets,rx_packets))
                    loss_ratio = round(loss_ratio*10**2,4)
                    graph[src_dpid][dst_dpid]['loss'] = loss_ratio
                else:
                    graph[src_dpid][dst_dpid]['loss'] = 0.0
        except:
            if self.awareness is None:
                self.awareness = lookup_service_brick('awareness')

    def create_bw_graph(self, bw_dict):
        """
            Save bandwidth data into networkx graph object.
        """
        try:
            graph = self.awareness.graph
            link_to_port = self.awareness.link_to_port
            for link in link_to_port:
                (src_dpid, dst_dpid) = link
                (src_port, dst_port) = link_to_port[link]
                if src_dpid in bw_dict and dst_dpid in bw_dict:
                    bw_src = bw_dict[src_dpid][src_port]
                    bw_dst = bw_dict[dst_dpid][dst_port]
                    bandwidth = min(bw_src, bw_dst)
                    # add key:value of bandwidth into graph.
                    graph[src_dpid][dst_dpid]['bandwidth'] = bandwidth
                else:
                    graph[src_dpid][dst_dpid]['bandwidth'] = 0
            return graph
        except:
            self.logger.info("Create bw graph exception")
            if self.awareness is None:
                self.awareness = lookup_service_brick('awareness')
            return self.awareness.graph

    def _save_freebandwidth(self, dpid, port_no, speed):
        # Calculate free bandwidth of port and save it.
        if self.port_features:
            port_state = self.port_features.get(dpid).get(port_no)
            if port_state:
                # capacity = port_state[2]
                capacity = 100
                curr_bw = self._get_free_bw(capacity, speed)
                curr_bw = round(curr_bw,4)
                self.free_bandwidth[dpid].setdefault(port_no, None)
                self.free_bandwidth[dpid][port_no] = curr_bw
            else:
                self.logger.info("Fail in getting port state")

    def _save_stats(self, _dict, key, value, length):
        if key not in _dict:
            _dict[key] = []
        _dict[key].append(value)

        if len(_dict[key]) > length:
            _dict[key].pop(0)

    def _get_speed(self, now, pre, period):
        if period:
            return (now - pre) / (period)
        else:
            return 0

    def _get_free_bw(self, capacity, speed):
        # BW:Mbit/s
        # return max(capacity/10**3 - speed * 8/10**6, 0)
        # BW:Kbit/s
        return max(capacity-speed*8/10**3,0)

    def _get_time(self, sec, nsec):
        return sec + nsec / (10 ** 9)

    def _get_period(self, n_sec, n_nsec, p_sec, p_nsec):
        return self._get_time(n_sec, n_nsec) - self._get_time(p_sec, p_nsec)

    @set_ev_cls(ofp_event.EventOFPEchoReply, MAIN_DISPATCHER)
    def echo_reply_handler(self, ev):
        """
            Handle the echo reply msg, and get the latency of link.
        """
        now_timestamp = time.time()
        try:
            latency = now_timestamp - eval(ev.msg.data)
            self.echo_latency[ev.msg.datapath.id] = latency
        except:
            return

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """
            Parsing LLDP packet and get the delay of link.
        """
        msg = ev.msg
        try:
            src_dpid, src_port_no = LLDPPacket.lldp_parse(msg.data)
            dpid = msg.datapath.id
            if self.sw_module is None:
                self.sw_module = lookup_service_brick('switches')

            for port in self.sw_module.ports.keys():
                if src_dpid == port.dpid and src_port_no == port.port_no:
                    delay = self.sw_module.ports[port].delay
                    self._save_lldp_delay(src=src_dpid, dst=dpid,
                                          lldpdelay=delay)
        except LLDPPacket.LLDPUnknownFormat as e:
            return

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        """
            Save flow stats reply info into self.flow_stats.
            Calculate flow speed and Save it.
        """
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        self.stats['flow'][dpid] = body
        self.flow_stats.setdefault(dpid, {})
        self.flow_speed.setdefault(dpid, {})
        for stat in sorted([flow for flow in body if flow.priority == 1],
                           key=lambda flow: (flow.match.get('in_port'),
                                             flow.match.get('ipv4_dst'))):
            # print(stat)
            key = (stat.match['in_port'],  stat.match.get('ipv4_dst'),
                   stat.instructions[0].actions[-1].port)
            value = (stat.packet_count, stat.byte_count,
                     stat.duration_sec, stat.duration_nsec)
            self._save_stats(self.flow_stats[dpid], key, value, 5)
            self.link_loss[dpid][(stat.match.get('ipv4_src'),stat.match.get('ipv4_dst'))] = stat.packet_count
            # Get flow's speed.
            pre = 0
            period = setting.MONITOR_PERIOD
            tmp = self.flow_stats[dpid][key]
            if len(tmp) > 1:
                pre = tmp[-2][1]
                period = self._get_period(tmp[-1][2], tmp[-1][3],
                                          tmp[-2][2], tmp[-2][3])

            speed = self._get_speed(self.flow_stats[dpid][key][-1][1],
                                    pre, period)

            self._save_stats(self.flow_speed[dpid], key, speed, 5)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        """
            Save port's stats info
            Calculate port's speed and save it.
        """
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        self.stats['port'][dpid] = body
        self.free_bandwidth.setdefault(dpid, {})

        for stat in sorted(body, key=attrgetter('port_no')):
            # self.link_loss[dpid][stat.port_no] = [stat.rx_packets,stat.tx_packets]
            port_no = stat.port_no
            if port_no != ofproto_v1_3.OFPP_LOCAL:
                key = (dpid, port_no)
                value = (stat.tx_bytes, stat.rx_bytes, stat.rx_errors,
                         stat.duration_sec, stat.duration_nsec)

                self._save_stats(self.port_stats, key, value, 5)

                # Get port speed.
                pre = 0
                period = setting.MONITOR_PERIOD
                tmp = self.port_stats[key]
                if len(tmp) > 1:
                    pre = tmp[-2][0] + tmp[-2][1]
                    period = self._get_period(tmp[-1][3], tmp[-1][4],
                                              tmp[-2][3], tmp[-2][4])

                speed = self._get_speed(
                    self.port_stats[key][-1][0] + self.port_stats[key][-1][1],
                    pre, period)

                self._save_stats(self.port_speed, key, speed, 5)
                self._save_freebandwidth(dpid, port_no, speed)

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def port_desc_stats_reply_handler(self, ev):
        """
            Save port description info.
        """
        msg = ev.msg
        dpid = msg.datapath.id
        ofproto = msg.datapath.ofproto

        config_dict = {ofproto.OFPPC_PORT_DOWN: "Down",
                       ofproto.OFPPC_NO_RECV: "No Recv",
                       ofproto.OFPPC_NO_FWD: "No Farward",
                       ofproto.OFPPC_NO_PACKET_IN: "No Packet-in"}

        state_dict = {ofproto.OFPPS_LINK_DOWN: "Down",
                      ofproto.OFPPS_BLOCKED: "Blocked",
                      ofproto.OFPPS_LIVE: "Live"}

        ports = []
        for p in ev.msg.body:
            ports.append('port_no=%d hw_addr=%s name=%s config=0x%08x '
                         'state=0x%08x curr=0x%08x advertised=0x%08x '
                         'supported=0x%08x peer=0x%08x curr_speed=%d '
                         'max_speed=%d' %
                         (p.port_no, p.hw_addr,
                          p.name, p.config,
                          p.state, p.curr, p.advertised,
                          p.supported, p.peer, p.curr_speed,
                          p.max_speed))

            if p.config in config_dict:
                config = config_dict[p.config]
            else:
                config = "up"

            if p.state in state_dict:
                state = state_dict[p.state]
            else:
                state = "up"
            port_feature = (config, state, p.curr_speed)
            self.port_features[dpid][p.port_no] = port_feature

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def _port_status_handler(self, ev):
        """
            Handle the port status changed event.
        """
        msg = ev.msg
        reason = msg.reason
        port_no = msg.desc.port_no
        dpid = msg.datapath.id
        ofproto = msg.datapath.ofproto

        reason_dict = {ofproto.OFPPR_ADD: "added",
                       ofproto.OFPPR_DELETE: "deleted",
                       ofproto.OFPPR_MODIFY: "modified", }

        if reason in reason_dict:

            print "switch%d: port %s %s" % (dpid, reason_dict[reason], port_no)
        else:
            print "switch%d: Illeagal port state %s %s" % (port_no, reason)

    def show_stat(self):
        weight_lst = ['delay','bandwidth','loss']
        flag = False
        min_dict = {}
        max_dict = {}
        min_delay = min_bw = min_loss = 1000
        max_delay = max_bw = max_loss = -1000
        if setting.TOSHOW and self.awareness is not None:
            print('###'*20)
            print('src     dst     delay(ms)     bandwidth(kbps)   loss(%)')
            print("###"*20)
            
            for src in self.awareness.graph:
                for dst in self.awareness.graph[src]:
                    d = [False for e in weight_lst if e not in self.awareness.graph[src][dst].keys()]
                    if not d:
                        flag = True           
                        delay = self.awareness.graph[src][dst]['delay']
                        max_delay = max(delay,max_delay)
                        min_delay = min(delay,min_delay)
                        bw = self.awareness.graph[src][dst]['bandwidth']
                        max_bw = max(bw,max_bw)
                        min_bw = min(bw,min_bw)
                        loss = self.awareness.graph[src][dst]['loss']
                        max_loss = max(loss,max_loss)
                        min_loss = min(loss,min_loss)
                        print("|{}<------>{}|      |{:<10}      |{:<10}      |{:<10}".format(src,dst,delay,bw,loss))

            if flag and max_loss!=min_loss:
                min_dict['delay'],min_dict['bw'],min_dict['loss'] = min_delay,min_bw,min_loss
                max_dict['delay'],max_dict['bw'],max_dict['loss'] = max_delay,max_bw,max_loss
                self.Min_Max(self.awareness.graph,min_dict,max_dict)

    def get_G(self):
        return self._graph

    def Min_Max(self,G,min_dict,max_dict):
        self.identify = True
        self._graph = nx.Graph()
        sub_delay = max_dict['delay']-min_dict['delay']
        sub_bw = max_dict['bw']-min_dict['bw']
        sub_loss = max_dict['loss']-min_dict['loss']
        print('###'*20)
        print('MIN-MAX')
        print("###"*20)
        s2d_lst = [(s,d) for s in G for d in G[s] if s!=d]
        for e in s2d_lst:
            if (e[1],e[0]) in s2d_lst:
                s2d_lst.remove((e[1],e[0]))      
        for s,d in s2d_lst:
            _delay = round((G[s][d]['delay']-min_dict['delay'])*10/sub_delay,4)   
            _bw = round(10-(G[s][d]['bandwidth']-min_dict['bw'])*10/sub_bw,4)
            _loss = round((G[s][d]['loss']-min_dict['loss'])*10/sub_loss,4)
            self._graph.add_edge(s,d,delay=_delay)
            self._graph.add_edge(s,d,bw=_bw)
            self._graph.add_edge(s,d,loss=_loss)
            print("|{}<------>{}|      |{:<10}      |{:<10}      |{:<10}".format(s,d,_delay,_bw,_loss))