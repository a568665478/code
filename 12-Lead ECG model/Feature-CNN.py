import torch
import math
import numpy as np
import scipy.io as sci
import torch.nn as nn
import os
import h5py
import torch.nn.functional as F
from torch.autograd import Variable
import torch.utils.data as Data
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

torch.cuda.set_device(1)
use_cuda = torch.cuda.is_available()

N, T ,D ,L, O= 100, 10, 200 ,8 ,2	#batch_size, seq_length , word_dim	,leads
hidden_size = 50

###############################################################################
class TrainDataset(Data.Dataset):
    def __init__(self):
        a=np.array(h5py.File('/home/lu/code/pytorch/data_dir/traindata.mat')['traindata'])
        #b=np.array(h5py.File('/home/lu/code/pytorch/data_dir/data11.mat')['train_data1'])
        self.data = np.transpose(a)

    def __getitem__(self, idx):
        
        data_ori = torch.from_numpy(self.data[idx])
        data = data_ori[0:16000]
        label = data_ori[16000]
        return data, label

    def __len__(self):
        return len(self.data)

trainset = TrainDataset()
train_loader = Data.DataLoader(trainset, batch_size = N,shuffle = True)

################################################################################
class TestDataset(Data.Dataset):
    def __init__(self):
        a=np.array(h5py.File('/home/lu/code/pytorch/data_dir/testdata.mat')['testdata'])
        #b=np.array(h5py.File('/home/lu/code/pytorch/data_dir/data11.mat')['test_data1'])
        self.data = np.transpose(a)

    def __getitem__(self, idx):
        
        data_ori = torch.from_numpy(self.data[idx])
        data = data_ori[0:16000]
        label = data_ori[16000]
        return data, label

    def __len__(self):
        return len(self.data)

testset = TestDataset()
test_loader = Data.DataLoader(testset, batch_size = 1, shuffle = True)

##################################################
class CNN(nn.Module):
    def __init__(self, hidden_size, output_size, n_layers=1, dropout_p=0.001, max_length=L):
        super(CNN, self).__init__()
        self.hidden_size = hidden_size
        self.output_size = output_size
        self.n_layers = n_layers
        self.dropout_p = dropout_p
        self.max_length = max_length
        self.dropout = nn.Dropout(self.dropout_p)

        self.conv1 = nn.Conv2d(1,4,(1,5),(1,2))
        self.conv2 = nn.Conv2d(4,8,(1,5),(1,2))
        self.conv3 = nn.Conv2d(8,16,(1,4),(1,2))
        #self.conv4 = nn.Conv2d(3,1,10)


        self.fc1 = nn.Linear(3712, self.hidden_size)
        self.out = nn.Linear(self.hidden_size, self.output_size)

    def forward(self, encoder_outputs):
        #print(encoder_outputs)
        cnn_out = F.max_pool2d(F.relu(self.conv1(encoder_outputs)),(1,3),(1,2))
        cnn_out = F.max_pool2d(F.relu(self.conv2(cnn_out)),(1,3),(1,2))
        cnn_out = F.max_pool2d(F.relu(self.conv3(cnn_out)),(1,3),(1,2))
        #cnn_out = F.max_pool1d(F.sigmoid(self.conv4(cnn_out)),2)
        #print(cnn_out)
        cnn_out = cnn_out.view(-1,3712)
        output = F.relu(self.fc1(cnn_out))
        #output = self.out(output)
        
        return output

class RNN(nn.Module):
    def __init__(self, input_size, hidden_szie1, hidden_szie2, output_size):
        super(RNN, self).__init__()
        
        self.rnn = nn.LSTM(input_size, hidden_szie1, 1, dropout = 0.3)
        self.r2h = nn.Linear(hidden_szie1, hidden_szie2)
        self.h2o = nn.Linear(hidden_szie2, output_size)

    def forward(self, input):
        hidden, _ = self.rnn(input)
        fc1 = F.relu(self.r2h(hidden[T-1]))
        output = self.h2o(fc1)
        #output = F.softmax(output)

        return output 


def train(input_variable, target_variable, cnn, cnn_optimizer, rnn, rnn_optimizer, criterion):

    cnn_optimizer.zero_grad()
    rnn_optimizer.zero_grad()

    loss = 0
    cnn_output = cnn(input_variable)
    cnn_output = cnn_output.view(N, T, D).transpose(0,1)
    rnn_output = rnn(cnn_output)
    loss = criterion(rnn_output, target_variable)
    loss.backward()

    cnn_optimizer.step()
    rnn_optimizer.step()

    return loss.data[0]

def test(input_variable, cnn, rnn):
    
    cnn_output = cnn(input_variable)
    cnn_output = cnn_output.view(1, T, D).transpose(0,1)
    rnn_output = rnn(cnn_output)
    top_n, top_i = rnn_output.data.topk(1)

    return top_i[0][0]

def trainIters(cnn, rnn, epoch, learning_rate=0.001):

    n_epochs = epoch
    current_loss = 0
    all_losses = []
    err_rate = []
    confusion = torch.zeros(6, 6)
    err = 0

    cnn_optimizer = torch.optim.Adam(cnn.parameters(), lr=learning_rate)
    rnn_optimizer = torch.optim.Adam(rnn.parameters(), lr=learning_rate)

    criterion = nn.CrossEntropyLoss()

    for epoch in range(1, n_epochs+1):
        for step1,(batch_x, batch_y) in enumerate(train_loader):

            batch_x = Variable(batch_x.type('torch.cuda.FloatTensor'))
            batch_y = Variable(batch_y.type('torch.cuda.LongTensor'))
            loss = train(batch_x.view(N,1,L,-1), batch_y, cnn, cnn_optimizer, rnn, rnn_optimizer, criterion)
            current_loss += loss

        for step2,(test_x, test_y) in enumerate(test_loader):

            test_x = Variable(test_x.type('torch.cuda.FloatTensor'))
            test_y = test_y.type('torch.cuda.LongTensor')
            guess = test(test_x.view(1,1,L,-1), cnn, rnn)
            confusion[guess][test_y[0]] += 1
        
        sen = (confusion[0][0])/((confusion[0][0]+confusion[0][1]))
        acc = (confusion[0][0]+confusion[1][1])/step2
        
        all_losses.append(current_loss / step1)
        err_rate.append(acc*100)
        
        current_loss = 0
        print('%d epoch: acc = %.2f, sen = %.2f%%'%(epoch, acc*100, sen*100))
        err = 0   
        confusion = torch.zeros(2,2)

    plt.figure()
    plt.plot(all_losses)
    plt.title('loss')
    plt.figure()
    plt.plot(err_rate)
    plt.title('err')

    print(confusion)
    fig = plt.figure()
    ax = fig.add_subplot(111)
    cax = ax.matshow(confusion.numpy())
    fig.colorbar(cax)

    plt.show()


cnn = CNN(2000, 2)
rnn = RNN(D, D, 100, 2)

if use_cuda:
    cnn = cnn.cuda()
    rnn = rnn.cuda()
trainIters(cnn, rnn, 50)
