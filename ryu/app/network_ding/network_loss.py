from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER,DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.base.app_manager import lookup_service_brick
from ryu.lib import hub
from ryu.base import app_manager
from operator import attrgetter
import setting

class PortMonitor(app_manager.RyuApp):
    def __init__(self,*args,**kwargs):
        super(PortMonitor,self).__init__(*args,**kwargs)
        self.datapaths = {}
        self.link_loss = {}
        self.awareness = lookup_service_brick('awareness')
        self.graph = None
        self.loss_thread = hub.spawn(self._monitor)
        self.save_loss_thread = hub.spawn(self._save_loss)

    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if not datapath.id in self.datapaths:
                self.logger.debug('Register datapath: %016x', datapath.id)
                self.datapaths[datapath.id] = datapath
                self.link_loss.setdefault(datapath.id,{})
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.debug('Unregister datapath: %016x', datapath.id)
                del self.datapaths[datapath.id]

    def _monitor(self):
        while setting.WEIGHT=='loss':
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(10)
            self.show_loss_graph()
            hub.sleep(1)
        
    def _request_stats(self,datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPPortStatsRequest(datapath,0,ofproto.OFPP_ANY)
        datapath.send_msg(req)

    def _save_loss(self):
        while setting.WEIGHT == 'loss':
            self.graph = self.get_loss()
            hub.sleep(setting.LOSS_PERIOD)
        

    def get_loss(self):
        graph = self.awareness.graph
        link_to_port = self.awareness.link_to_port
        for link in link_to_port:
            (src_dpid,dst_dpid) = link
            (src_port,dst_port) = link_to_port[link]
            if src_dpid in self.link_loss and dst_dpid in self.link_loss:
                if self.link_loss[src_dpid] and self.link_loss[dst_dpid]:
                    # print(self.link_loss[src_dpid][src_port][1])
                    # print(self.link_loss[dst_dpid][dst_port][0])
                    tx_packets = self.link_loss[src_dpid][src_port][1]
                    rx_packets = self.link_loss[dst_dpid][dst_port][0]
                    loss_ratio = (tx_packets-rx_packets)/float(tx_packets)
                    #print(loss_ratio)
                    graph[src_dpid][dst_dpid]['loss'] = loss_ratio
                    # print(graph[src_dpid][dst_dpid]['loss'])
            else:
                graph[src_dpid][dst_dpid]['loss'] = 0.0
        return graph

    def show_loss_graph(self):
        if setting.TOSHOW is False:
            return
        print('-----------------------Link   Loss---------------------------------------')
        print('src           ''           dst          ''            loss ratio         ')
        print('-------------------------------------------------------------------------')
        graph = self.awareness.graph
        link_to_port = self.awareness.link_to_port
        for link in link_to_port:
            (src_dpid, dst_dpid) = link
            (src_port, dst_port) = link_to_port[link]
            if 'loss' in graph[src_dpid][dst_dpid]:
                link_los = graph[src_dpid][dst_dpid]['loss']
                print('%016x:%2x---->%016x:%2x    %5.12f'%(src_dpid,src_port,dst_dpid,dst_port,link_los))

    @set_ev_cls(ofp_event.EventOFPPortStatsReply,MAIN_DISPATCHER)
    def _port_stats_reply_handler(self,ev):
        if setting.WEIGHT=='loss':
            body = ev.msg.body
            self.logger.info('---------------------------------------------------------------')
            self.logger.info('datapath          port     '
                            'rx-pkts     rx-bytes    tx-pkts     tx-bytes')
            self.logger.info('----------------------------------------------------------------')
            for stat in sorted(body,key=attrgetter('port_no')):
                self.logger.info('%016x %8x %8d %8d %8d %8d',ev.msg.datapath.id,stat.port_no,stat.rx_packets,stat.rx_bytes,
                                    stat.tx_packets,stat.tx_bytes)
                self.link_loss[ev.msg.datapath.id][stat.port_no] = [stat.rx_packets,stat.tx_packets]

