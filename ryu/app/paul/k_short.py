import networkx as nx

class K_Short:
    def __init__(self,_G,src,dst):
        self.G = _G
        self.s = src
        self.d = dst
        self.path_weight = {}
        self.paths = []
               
    def min_cost_path(self,delay_threshold,cost_threshold):
        #time complexity of shortest_simple_paths functon is O(n^3)
        paths = list(nx.shortest_simple_paths(self.G,self.s,self.d,weight='delay'))[:6]
        for path in paths:
            sum_delay = 0
            sum_cost = 0
            for ind in range(len(path)-1):
                sum_delay += self.G[path[ind]][path[ind+1]]['delay']
                sum_cost += (self.G[path[ind]][path[ind+1]]['bw']+self.G[path[ind]][path[ind+1]]['loss'])/2
            self.path_weight[tuple(path)] = [sum_delay,sum_cost]           
        
        sorted_delay_path = sorted(self.path_weight.items(),key=lambda x: x[1][0])

        for k in sorted_delay_path:
            if k[1][0]<=delay_threshold and k[1][1]<=cost_threshold:
                self.paths.append(list(k[0]))

        print('k-sort paths',self.paths)
        
        if len(self.paths)==0:
            print("there is no feasible path")
            return None 
        return self.paths          