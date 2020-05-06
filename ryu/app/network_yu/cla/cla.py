#! /usr/bin/python3
import csv
import numpy as np
from sklearn.externals import joblib

class Cla:
    
    def __init__(self,numSimple=250,wFlag = True):
        
        #self.threshold = threshold
        self.wFlag = wFlag
        self.numSimple = numSimple
        self.dataSet = []
        self.new_gaussian = joblib.load('GaussianNB.pkl')
        
    def en_queue(self,key,data):
        data = np.array(data)
        row = data.shape[0]
        print("the row value of flow is %d" % row)
        # sorted the matrix by timestamp
        data = data[data[:,1].argsort()]
        len_data = data[:,0].flatten()
        time_data = data[:,1].flatten()
        # calcute mean and std value of length
        len_mean = np.mean(len_data)
        len_std = np.std(len_data,ddof=1)

        inter_lst = []

        # calcute packet size transform count
        count = 0
        for i in range(len(len_data)-1):
            inter_time = time_data[i+1] - time_data[i]
            inter_lst.append(inter_time)# add record to list
            if len_data[i] != len_data[i+1]:
                count = count + 1

         # calcute time interval mean and std
        time_mean = np.mean(inter_lst)
        time_std = np.std(inter_lst,ddof=1)
        if self.wFlag:
            feature_info = [len_mean,len_std,time_mean,time_std,count]
            res = self.indentify(feature_info)
            count = 0
            return 0,res
        else:
            self.dataSet.append([len_mean,len_std,time_mean,time_std,count])
            count = 0

            print("finish appending %dth record" % len(self.dataSet))
            if len(self.dataSet) == self.numSimple:
                if self.write(self.dataSet):
                    print("finish writing")
                    return 2          
            return 1
        
    def write(self,dataSet):
        df = []
        #for i,key in enumerate(self.data_feature.keys()):
        #print("the length of dataSet is %d" % len(self.data_feature[packet_info]))
        for ele in dataSet:
            df.append(ele+[2])
        
        with open("f2.csv","w") as csvfile: 
            writer = csv.writer(csvfile)  
            writer.writerow(["l_mean","l_std","t_mean","t_std","count","class"]) 
            writer.writerows(df)

        return True

    def identify(self,feature_info):

        res = self.new_gaussian.predict(np.array(feature_info))
        return res[0]
    # def predict(self,packet_info,path):
    #     model = joblib.load(path)
    #     res = model.predict(np.array(self.flow_feature[packet_info]))   