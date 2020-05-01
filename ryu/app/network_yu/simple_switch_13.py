# Copyright (C) 2011 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4
from ryu.lib.packet import tcp,udp
from ryu.lib.packet import ether_types
import time
import array
from cla import Cla


class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {1:{'00:00:00:00:00:01':1,'00:00:00:00:00:02':2,'00:00:00:00:00:03':3,'00:00:00:00:00:04':4}}
        self.p_num = {}
        self.dataSet = {}
        self.packet_lst = []
        self.host_lst = []
        self.flag = False
        self.pre_time = 0
        self.cla = Cla(threshold=200,numSimple=500)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath,0, match, actions)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)

    def packet_feature(self,msg,ip_src,ip_dst):
        """
            Get the packet tuple info and packet feature info
        """
        p_dict = {}
        #pkt = packet.Packet(msg.data)
        pkt = packet.Packet(array.array('B',msg.data))
        for p in pkt:
            p_dict[p.protocol_name] = p
            if p.protocol_name in ['tcp','udp']:
                tran_type = p.protocol_name
                port_src = p.src_port
                port_dst = p.dst_port
                length = len(msg.data)
                timestamp = time.time()
                return (ip_src,port_src,ip_dst,port_dst,tran_type),(length,timestamp)

        return None  

    def feed_data(self,result):

        key,value = result[0],result[1]
        #sub_time = value[1] - self.pre_time
        #self.pre_time = value[1]
        if key not in self.packet_lst:
            self.packet_lst.append(key)
            self.dataSet.setdefault(key,[])
            #self.p_num[key] = 0

        # if self.p_num[key] == 0:
        #     value_lst = [value[0],0]
        # else:
        #     value_lst = [value[0],sub_time]

        self.dataSet[key].append(list(value))
        #self.p_num[key] = self.p_num[key] + 1
        length_packet = len(self.dataSet[key])
        if length_packet == 200:
            print("the length of dataSet is: %d" % len(self.dataSet[key]))
            #self.pre_time = 0
            #self.p_num[key] = 0#initiaziong count
            
            ret = self.cla.en_queue(key,self.dataSet[key])
            self.dataSet[key][:] = []
            return ret
        
        return 0


    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        # If you hit this you might want to increase
        # the "miss_send_length" of your switch
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug("packet truncated: only %s of %s bytes",
                              ev.msg.msg_len, ev.msg.total_len)
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        dst = eth.dst
        src = eth.src
       # dpid = format(datapath.id, "d").zfill(16)
        dpid = datapath.id
        
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        if (src,dst) not in self.host_lst:
            self.host_lst.append((src,dst))      
            match = parser.OFPMatch(in_port=in_port,eth_dst = dst,eth_src=src)
            if dst == '00:00:00:00:00:01':
                actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,ofproto.OFPCML_NO_BUFFER)]
                self.add_flow(datapath,2,match,actions)

            else:
                actions = [parser.OFPActionOutput(out_port)]
                # install a flow to avoid packet_in next time
                if out_port != ofproto.OFPP_FLOOD:
                    match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
                    # verify if we have a valid buffer_id, if yes avoid to send both
                    # flow_mod & packet_out
                    if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                        self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                        return
                    else:
                        self.add_flow(datapath, 1, match, actions)

        elif dst == '00:00:00:00:00:01' and self.flag==False:
            out_port = 1
            if isinstance(ip_pkt,ipv4.ipv4):         
                res = self.packet_feature(msg,ip_pkt.src,ip_pkt.dst)
                if res:
                    self.flag = True #stop packet go forward to dataSet
                    ret = self.feed_data(res)
                    self.flag = False#start leting packet enter dataSet
                    if ret == 2:
                        self.flag = True
        # send pack-out message to datapath
        actions = [parser.OFPActionOutput(out_port)]
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
