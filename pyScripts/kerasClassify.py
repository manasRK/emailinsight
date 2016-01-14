from __future__ import print_function
import numpy as np
import pandas as pd
import os
import time
import pprint
import cPickle

from keras.callbacks import RemoteMonitor
from keras.layers.recurrent import LSTM,GRU
from keras.preprocessing import sequence
from keras.models import Sequential
from keras.layers.core import Dense, Dropout, Activation
from keras.optimizers import SGD, Adam, RMSprop
from keras.preprocessing.text import Tokenizer
from keras.layers.embeddings import Embedding
from keras.utils import np_utils
from mboxConvert import parseEmails,getEmailStats,mboxToBinaryCSV
from kerasPlotter import Plotter

def get_keras_features(emails,verbose=True,nb_words=5000,skip_top=0,maxlen=None,as_matrix=True, matrix_type='count', label_cutoff=0.01):
    (totalWordsCount,fromCount,domainCount,labels) = getEmailStats(emails)
    if verbose:
        print('Creating email dataset with labels %s '%str(labels))
        print('Label word breakdown:')
        total = 0
        for label in labels:
            count = sum(totalWordsCount[label].values())
            total+=count
            print('\t%s:%d'%(label,count))
        print('Total word count: %d'%total)

    labelCounts = {label:0 for label in labels}
    for email in emails:
        labelCounts[email.label]+=1
    cutoff = int(len(emails)*label_cutoff)
    removed = 0
    for label in labels[:]:
        if labelCounts[label]<cutoff:
            removed+=1
            labels.remove(label)
    labelNums = {labels[i]:i for i in range(len(labels))}
    if verbose:
        print('Found %d labels below count threshold of %d '%(removed,cutoff))
    if verbose:
        print('Creating email dataset with labels %s '%str(labels))
        print('Label email count breakdown:')
        total = 0
        for label in labels:
            print('\t%s:%d'%(label,labelCounts[label]))
        print('Total emails: %d'%sum([labelCounts[label] for label in labels]))
    
    texts = []
    emailLabels = []
    for email in emails:
        if email.label not in labels:
            continue
        text = email.sender+" "+str(email.subject)
        text+= email.fromDomain
        text+=email.content
        texts.append(text.replace('\n','').replace('\r',''))
        emailLabels.append(labelNums[email.label])
    emailLabels = np.array(emailLabels)
    tokenizer = Tokenizer(nb_words)
    tokenizer.fit_on_texts(texts)
    reverse_word_index = {tokenizer.word_index[word]:word for word in tokenizer.word_index}
    word_list = [reverse_word_index[i+1] for i in range(nb_words)]
    if as_matrix:
        feature_matrix = tokenizer.texts_to_matrix(texts, mode=matrix_type)
        return feature_matrix,emailLabels,word_list,labels
    else:
        sequences = tokenizer.texts_to_sequences(texts)
        return sequences,emailLabels,word_list,labels

def write_csv(csvfile, feature_matrix, labels,feature_names=None, verbose=True):
    dataframe = pd.DataFrame(data=feature_matrix,columns=feature_names)
    dataframe['label'] = labels
    dataframe.to_csv(csvfile)
    if verbose:
        print('Wrote CSV with columns %s to %s'%(str(dataframe.columns),csvfile))

def read_csv(csvfile,verbose=True):
    dataframe = pd.read_csv(csvfile,header=0)
    labels = dataframe[u'label'].tolist()
    if verbose:
        print('Read CSV with columns %s'%str(dataframe.columns))
    dataframe.drop(u'label',inplace=True,axis=1)
    if u'Unnamed: 0' in dataframe.columns:
        dataframe.drop(u'Unnamed: 0',inplace=True,axis=1)
    feature_matrix = dataframe.as_matrix()
    feature_names = dataframe.columns
    return feature_matrix,labels,feature_names

def write_info(txtfile, label_names, verbose=True):
    with open(txtfile,'w') as writeto:
        writeto.write(','.join(label_names))

def read_info(txtfile,verbose=True):
    with open(txtfile,'r') as readfrom:
        label_names=readfrom.readline().split(',')
    return label_names

def write_sequences(txtfile, sequences, labels, verbose=True):
    with open(txtfile,'w') as writeto:
        for sequence,label in zip(sequences,labels):
            #lol random demarcation markers so fun amirite
            writeto.write(','.join([str(x) for x in sequence])+';;;'+str(label)+'\n')
    if verbose:
        print('Wrote txt with %d lines'%len(sequences))

def read_sequences(txtfile,verbose=True):
    sequences = []
    labels = []
    linesnum = 0
    with open(txtfile,'r') as readfrom:
        for line in readfrom:
            linesnum+=1
            parts = line.split(';;;')
            split = parts[0].split(',')
            if len(split)<=1:
                continue
            sequences.append(np.asarray(split))
            labels.append((int)(parts[1]))
    if verbose:
        print('Read txt with %d lines'%linesnum)
    return sequences,labels

    dataframe = pd.read_csv(csvfile,header=0)
    labels = dataframe[u'label'].tolist()
    if verbose:
        print('Read CSV with columns %s'%str(dataframe.columns))
    dataframe.drop('label',inplace=True,axis=1)
    feature_matrix = dataframe.as_matrix()
    return feature_matrix,labels

def make_dataset(features,labels,num_labels,test_split=0.1,nb_words=1000):
    if type(features)==list:
        num_examples = len(features)
        random_order = np.random.permutation(num_examples)
        index_split = (int)(test_split*num_examples)
        train_indices = random_order[index_split:]
        test_indices = random_order[:index_split]
        X_train = [features[i] for i in train_indices]
        X_test = [features[i] for i in test_indices]
        Y_train = [labels[i] for i in train_indices]
        Y_test = [labels[i] for i in test_indices]
    else:
        num_examples = features.shape[0]
        random_order = np.random.permutation(num_examples)
        index_split = (int)(test_split*num_examples)
        train_indices = random_order[index_split:]
        test_indices = random_order[:index_split]
        X_train = features[train_indices]
        X_test = features[test_indices]
        Y_train = [labels[i] for i in train_indices]
        Y_test = [labels[i] for i in test_indices]
    Y_train_c = np_utils.to_categorical(Y_train, num_labels)
    Y_test_c = np_utils.to_categorical(Y_test, num_labels)
    return ((X_train,Y_train_c),(X_test,Y_test_c)),Y_train,Y_test

def get_emails(verbose=True):
    picklefile = 'pickled_emails.pickle'
    if os.path.isfile(picklefile):
        with open(picklefile,'r') as load_from:
            emails = cPickle.load(load_from)
    else:
        emails = parseEmails('.',printInfo=verbose)
        with open(picklefile,'w') as store_to:
            cPickle.dump(emails,store_to)
    return emails

def get_keras_data(num_words=1000,matrix_type='binary',verbose=True):
    #yeah yeah these can be separate functions, but lets just bundle it all up
    csvfile = 'keras_data_%d_%s.csv'%(num_words,str(matrix_type))
    infofile = 'data_info.txt'
    if os.path.isfile(csvfile):
        features,labels,feature_names = read_csv(csvfile,verbose=verbose)
        label_names = read_info(infofile)
    else:
        emails = get_emails(verbose=verbose)
        features,labels,feature_names,label_names = get_keras_features(emails,nb_words=num_words,matrix_type=matrix_type,verbose=verbose)
        write_csv(csvfile,features,labels,feature_names,verbose=verbose)
        write_info(infofile,label_names)
    return features,labels,feature_names,label_names

def get_my_data(per_label=False):
    csvfile = 'my_data_%s.csv'%str(per_label)
    infofile = 'data_info.txt'
    if os.path.isfile(csvfile):
        features,labels,feature_names = read_csv(csvfile)
        label_names = read_info(infofile)
    else:
        mboxToBinaryCSV('.',csvfile,perLabel=per_label)
        features,labels,feature_names = read_csv(csvfile)#legacy code etc.
        label_names = list(set(labels))
        write_info(infofile,label_names)
    num_labels = max(labels)+1
    return features,labels,feature_names,label_names
        
def get_sequence_data():
    txtfile = 'sequence_data.txt'
    if os.path.isfile(txtfile):
        features,labels = read_txt(txtfile)
    else:
        emails = parseEmails('.')
        features,labels,words,labelVals = get_keras_features(emails,as_matrix=False)
        write_txt(txtfile,features,labels)
    num_labels = max(labels)+1
    return features,labels,num_labels

def evaluate_mlp_model(dataset,num_classes,extra_layers=0,num_hidden=512,dropout=0.5,graph_to=None,verbose=True):
    (X_train, Y_train), (X_test, Y_test) = dataset
    batch_size = 32
    nb_epoch = 5
    
    if verbose:
        print(len(X_train), 'train sequences')
        print(len(X_test), 'test sequences')
        print('X_train shape:', X_train.shape)
        print('X_test shape:', X_test.shape)
        print('Y_train shape:', Y_train.shape)
        print('Y_test shape:', Y_test.shape)
        print('Building model...')
    model = Sequential()
    model.add(Dense(num_hidden, input_shape=(X_train.shape[1],)))
    model.add(Activation('relu'))
    model.add(Dropout(dropout))
    for i in range(extra_layers):
        model.add(Dense(num_hidden, input_shape=(X_train.shape[1],)))
        model.add(Activation('relu'))
        model.add(Dropout(dropout))
    model.add(Dense(num_classes))
    model.add(Activation('softmax'))
    model.compile(loss='categorical_crossentropy', optimizer='adam')
    plotter = Plotter(save_to_filepath=graph_to, show_plot_window=True)
    callbacks = [plotter] if graph_to else []
    history = model.fit(X_train, Y_train, nb_epoch=nb_epoch, batch_size=batch_size, verbose=1 if verbose else 0, show_accuracy=True, validation_split=0.1,callbacks=callbacks)
    score = model.evaluate(X_test, Y_test, batch_size=batch_size, verbose=1 if verbose else 0, show_accuracy=True)
    if verbose:
        print('Test score:',score[0])
        print('Test accuracy:', score[1])
    predictions = model.predict_classes(X_test,verbose=1 if verbose else 0)
    return predictions,score[1]

def evaluate_lstm_model(dataset,num_classes):
    (X_train, Y_train), (X_test, Y_test) = dataset
    max_features = 20000
    maxlen = 125  # cut texts after this number of words (among top max_features most common words)
    batch_size = 32

    print(len(X_train), 'train sequences')
    print(len(X_test), 'test sequences')
    print("Pad sequences (samples x time) with maxlen %d"%maxlen)
    X_train = sequence.pad_sequences(X_train, maxlen=maxlen)
    X_test = sequence.pad_sequences(X_test, maxlen=maxlen)
    print('X_train shape:', X_train.shape)
    print('X_test shape:', X_test.shape)

    print('Build model...')
    model = Sequential()
    model.add(Embedding(max_features, 128, input_length=maxlen))
    model.add(GRU(400))  # try using a GRU instead, for fun
    model.add(Dropout(0.5))
    model.add(Dense(num_classes))
    model.add(Activation('softmax'))

    # try using different optimizers and different optimizer configs
    model.compile(loss='categorical_crossentropy',optimizer='adam')

    print("Train...")
    model.fit(X_train, Y_train, batch_size=batch_size, nb_epoch=15,
              validation_data=(X_test, Y_test), show_accuracy=True)
    score, acc = model.evaluate(X_test, Y_test,
                                batch_size=batch_size,
                                show_accuracy=True)
    if verbose:
        print('Test score:', score)
        print('Test accuracy:', acc)
    return score[1]
