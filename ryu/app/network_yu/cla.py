#import copy
#import pandas as pd
#from sklearn.externals import joblib
#from pandas import Series,DataFrame
import csv
import numpy as np

class Cla:
    
    def __init__(self,threshold=200,numSimple=1000,writeFlag=False):
        self.class_to_tos = {0:1,1:2,2:3}
        self.maxCount = threshold       #max value of packets in a flow
        self.writeFlag = writeFlag        #wether write to csv file
        self.num_simple = numSimple     #the num of simple in csv file

        #self.num = {}                   #()->int,describe the num of simple in data_feature
        self.count = {}                 #()->int,describe the num of packet in flow
        self.flow_info = {}             #()->{()->[],()->[]},store the feature of packet in flow
        self.flow_feature = {}          #()->[],store the feature of flow
        self.data_feature = {}          #()->[[]],store the features of mult-flow
        
    def en_queue(self,packet_info,feature_info):
        
        if packet_info not in self.flow_info.keys():
            self.flow_info.setdefault(packet_info,{})
            self.data_feature.setdefault(packet_info,[])
            self.flow_info[packet_info]["length"] = [feature_info[0]]
            self.flow_info[packet_info]["time"] = [feature_info[1]]
            self.count[packet_info] = 1
            #self.num[packet_info] = 0
            
        else:
            self.flow_info[packet_info]["length"].append(feature_info[0])
            self.flow_info[packet_info]["time"].append(feature_info[1])
            self.count[packet_info] = self.count[packet_info] + 1
            #print("count: %d" % self.count[packet_info])
            
        if self.count[packet_info] >= self.maxCount:
            #calcuting flow feature
            #print("calcuting flow feature")
            self.calcute(packet_info)
            if self.writeFlag:
                self.flow_info[packet_info]["length"][:] = []
                self.flow_info[packet_info]["time"][:] = []
                # judje 
                data_len = len(self.data_feature[packet_info]) #get the num of flow by packets
                if data_len % 10 == 0:
                    print("total %d simples is stored in dataFeature dic" % data_len)

                if data_len >= self.num_simple:
                    print("########writing feature to test.csv")
                    self.write(packet_info)
                    return True
                    
                    #self.num[packet_info] = 0
            self.count[packet_info] = 0
        return False
        
    def calcute(self,packet_info):
        count = 0
        lst_interval = []
        lst_length = self.flow_info[packet_info]["length"]
        lst_time = self.flow_info[packet_info]["time"]
        
        for ind in range(len(lst_length)-1):
            lst_interval.append(lst_time[ind+1]-lst_time[ind])
            if lst_length[ind] != lst_length[ind+1]:
                count = count + 1
        
        self.flow_feature[packet_info] = [np.mean(lst_length[:]),np.std(lst_length[:],ddof=1),np.mean(lst_interval[:]),np.std(lst_interval[:],ddof=1),count]
        self.data_feature[packet_info].append(self.flow_feature[packet_info])
        #self.num[packet_info] = self.num[packet_info] + 1
        self.flow_info[packet_info]
        
    def write(self,packet_info):
        df = []
        #for i,key in enumerate(self.data_feature.keys()):
        #print("the length of dataSet is %d" % len(self.data_feature[packet_info]))
        for ele in self.data_feature[packet_info]:
            df.append(ele+[0])
        
        with open("test.csv","w") as csvfile: 
            writer = csv.writer(csvfile)  
            writer.writerow(["l_mean","l_std","t_mean","t_std","count","class"]) 
            writer.writerows(df)

        del self.data_feature[packet_info]
        # df_csv = DataFrame(df,colums=['l_mean','l_std','t_mean','t_std','count'])
        # df_csv.to_csv('DataSet.csv')
        
    # def predict(self,packet_info,path):
    #     model = joblib.load(path)
    #     res = model.predict(np.array(self.flow_feature[packet_info]))   