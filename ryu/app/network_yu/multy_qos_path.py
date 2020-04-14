import networkx as nx
from math import sqrt,floor
import copy


class K_Approx:
    def __init__(self,_G):
        self.G = _G
        self.G_App = None
        self.pM = None
   
    def Approx(self,s,t,K,W):
        self.G_App = nx.Graph()
        for edge in self.G.edges():
            u,v = edge[0],edge[1]
            max_weight = max(self.G[u][v].values())/W
            self.G_App.add_edge(u,v,weight=max_weight) 
        
        self.pM=nx.dijkstra_path(self.G_App,source=s,target=t,weight='weight')
        return self.pM,self.G,self.G_App
        
class PseudoRMCP:
    def __init__(self,G,s,t,K,threshold):
        self.G = G
        self.s = s
        self.t = t
        self.K = K
        self.threshold = threshold
        self.DG = None
        self.pK = None
        
    def auxiDG(self):
        self.DG = nx.DiGraph()
        end_nodes = []
        paths = {} #(src_node,dst_node)-->[path]
        distance = {} #(src_node,dst_node)-->path_delay
        permutation = [[i,j] for i in range(0,self.threshold+1) for j in range(0,self.threshold+1)]
        
        #add nodes
        for node in self.G.nodes():
            sub_lst = [[node]+ele for ele in permutation]
            sub_tup = [tuple(ele) for ele in sub_lst]
            self.DG.add_nodes_from(sub_tup)
        
        #add edges
        for u,v in list(self.G.edges()):
            weight = self.G[u][v]
            u_f = list(filter(lambda x:x[0]==u,self.DG.nodes()))
            v_f = list(filter(lambda x:x[0]==v,self.DG.nodes()))
            edge_lst = [(i,j) for i in u_f for j in v_f if (j[1]-i[1])==weight['bw'] and (j[2]-i[2])==weight['loss']]
            edge_reserve_lst = [(i,j) for i in v_f for j in u_f if (j[1]-i[1])==weight['bw'] and (j[2]-i[2])==weight['loss']]
            self.DG.add_edges_from(edge_lst+edge_reserve_lst,delay=weight['delay'])

        #add des nodes
        des_nodes = [node for node in self.DG.nodes if node[0]==self.t]
        g = lambda x:x[1]+1 if x[1]==x[2] else max(x[1],x[2])
        for node in des_nodes:
            D = g(node)
            end_nodes.append(('t',D,D))
            pairs = (node,('t',D,D))
            self.DG.add_edge(*pairs,delay=0)
        #calcute shortest paths statify multy constrains
        source = (self.s,0,0)
        for target in set(end_nodes):
            if nx.has_path(self.DG,source,target):
                paths[(source,target)] = nx.dijkstra_path(self.DG,source,target,weight='delay')
                distance[(source,target)] = nx.dijkstra_path_length(self.DG,source,target,weight='delay')
                print('distance between {0} and {1}:{2}'.format(source,target,distance[(source,target)]))
        d_lst = [d[1][1] for d in distance.keys() if distance[d]<=d[1][1] and d[1][1]<=self.threshold]
        if len(d_lst)==0:
            print("There is no feasible path")
            return None
        self.pK = paths[(source,('t',min(d_lst),min(d_lst)))]
        print("The feasible path is: ",self.pK)
        return self.pK

class FPTAS_SMCP:
    def __init__(self,_G,s,t,K,W,e):
        self.LB = None
        self.UB = None
        self.pM,self.G,self.G_App = K_Approx(_G).Approx(s,t,K,W)
        self.s = s
        self.t = t
        self.K = K
        self.W = W
        self.DG = None
        self.Gtha = None
        self.n = nx.number_of_nodes(self.G)
        self.e = e
    
    def TEST(self,Gtha,tha,threshold,flag=False):     
        #build auxiliary graph
        for u,v in self.G.edges():
            Gtha[u][v]['delay'] = floor(Gtha[u][v]['delay']*tha)+1
            Gtha[u][v]['bw'] = floor(Gtha[u][v]['bw']*tha)+1
            Gtha[u][v]['loss'] = floor(Gtha[u][v]['loss']*tha)+1
            
        res = PseudoRMCP(Gtha,self.s,self.t,self.K,threshold).auxiDG()
       
        return res
    
    def SMCP(self):
        pM_edge = [(self.pM[i],self.pM[i+1]) for i in range(len(self.pM)-1)]
        wpM = 0
        self.Gtha = copy.deepcopy(self.G)
        
        for edge in pM_edge:
            u,v = edge[0],edge[1]
            wpM += self.G_App[u][v]['weight']
        if wpM == 0:
            print('The feasible path is:',self.pM)
            return
        #initalize
        self.LB = wpM/self.K    
        self.UB = wpM/2
        #adjust bound
        print('pM:',self.pM)
        print('the upper bound and low bound is:',self.UB,self.LB) 
#         g = lambda C,tha,threshold:self.LB=C if TEST(self.Gtha,tha,threshold)==False else self.UB=C 
        while self.UB>2*self.LB:
            C = sqrt(UB*LB)
            print('hello')
            tha = (self.n-1)/(C*self.W)
            threshold = floor(self.n-1)+self.n-1
            if self.TEST(self.Gtha,tha,threshold):
                self.UB = C
            else:
                self.LB = C
#             g(C,tha,threshold)
        tha = (self.n-1)/(self.LB*self.W*self.e)
        threshold = floor((2*self.UB*(self.n-1))/(self.LB*self.e))+self.n-1
        threshold = int(threshold)
        print('the tha {} and the threshold {} of graph Gtha'.format(tha,threshold))
        path = self.TEST(self.Gtha,tha,threshold,flag=True)
        return path