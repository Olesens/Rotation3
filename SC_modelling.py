import pandas as pd
import numpy as np
import pickle
import matplotlib.pyplot as plt
import statsmodels.api as sm
import math
from scipy.optimize import curve_fit
from Plotting_functions import clean_up_df, cal_prob
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.linear_model import LogisticRegressionCV
from sklearn.feature_selection import RFE
from sklearn.metrics import roc_auc_score
from sklearn.metrics import roc_curve
from sklearn import preprocessing

from sklearn import metrics
import warnings
from statistics import mean
warnings.filterwarnings('ignore')

pickle_in = open("Rot3_data\\SC_full_df.pkl","rb")
Animal_df = pickle.load(pickle_in)
scaler = preprocessing.MinMaxScaler()  # define name for scaler used in cv_model functions

date_list_sc = ['2019-07-26', '2019-07-27', '2019-07-29', '2019-07-30', '2019-07-31',
       '2019-08-01', '2019-08-02', '2019-08-05', '2019-08-06', '2019-08-07',
       '2019-08-08', '2019-08-09', '2019-08-12', '2019-08-13', '2019-08-14',
       '2019-08-15', '2019-08-16', '2019-08-19', '2019-08-20', '2019-08-21',
       '2019-08-22', '2019-08-23', '2019-08-27', '2019-08-28', '2019-08-29',
       '2019-08-30', '2019-09-02', '2019-09-03', '2019-09-04', '2019-09-05',
       '2019-09-06', '2019-09-09', '2019-09-10', '2019-09-11', '2019-09-12',
       '2019-09-13', '2019-09-16']
# Generate dataframe of all relevant raw trials, exclude vio and tm trials
def trial_df(df, animal_id, date, ses_no=1):
    """
    From provided dataframe, animal_id and date extracts all non violation or timeout trials and generates
    new dataframe
    :param df: dateframe containing history of hits, side etc. for given animal and date
    :param animal_id: string, example 'AA08'
    :param date: string, pandas date format. Example: '2019-08-20'
    :param ses_no: session number is used to keep track of which trials are from which session, this is the number
                    that the function will put in the index for the given date.
    :return: dataframe with all relevant trials in.
    """

    history = cal_prob(df, animal_id, date, ret_hist=True)
    trial_index = 2  # we start from the second trial because the first trial doesn't have a previous trial
    trial_dict = {}

    # determine if animal went right or left
    history['went_right'] = 0  # add new column filled with zeros
    mask = (history['hits'] == 1) & (history['side'] == 114)  # correctly went right to stim (1,2 or 3)
    history['went_right'] = history['went_right'].mask(mask, 1)
    mask = (history['hits'] == 0) & (history['side'] == 108)  # incorrectly went right to stim (4,5 or 6)
    history['went_right'] = history['went_right'].mask(mask, 1)

    history['right_side_correct'] = 0
    mask = (history['side'] == 114)  # right side is correct choice
    history['right_side_correct'] = history['right_side_correct'].mask(mask, 1)

    # return history
    sensory_list = []  # I suppose I will still include sensory stim from non-hit trials in the mean.
    # trial[0] is side, trial[1] is stim, trial[2] is hit, trial[3] is went_right, trial[4] is correct side 1=right
    for tri_number in history.index._values[2:]:  # if it was not a tm or vio add it to dataset

        pprev_trial = history.ix[(tri_number - 2)]
        prev_trial = history.ix[(tri_number - 1)]
        if tri_number == 2:
            sensory_list.append(pprev_trial[1])  # if it is the first instance add the sensory stim from 2 trials back
        sensory_list.append(prev_trial[1])  # then add previous trials sensory stim

        # create unique index for the df
        trial = history.ix[tri_number]
        session = 'S' + str(ses_no) + '_'
        if np.isnan(trial[2]) == False:
            if np.isnan(prev_trial[2]) == False:
                key = str(session + str(trial_index))
                sen_mean = (mean(sensory_list))
                trial_dict[key] = [trial[3], trial[1], prev_trial[2], prev_trial[1], prev_trial[4], prev_trial[3],
                                       pprev_trial[1], sen_mean]
        trial_index += 1

    # create dict
    data_df = pd.DataFrame.from_dict(trial_dict,
                                     orient='index',
                                     columns=['Ct_wr', 'Ct_Stim', 'Pt_Hit', 'Pt_Stim', 'Pt_csr', 'Pt_wr', 'PPt_stim',
                                              'Lt_stim'])
    # csr = correct side right
    return data_df


def all_trials(df, animal_id, date_list, dummies=True):
    session_list = []
    session_index = 1
    for session in date_list:
        print('date is: ' +  str(session))
        try:
            trials = trial_df(df, animal_id, session, ses_no = session_index)
            session_list.append(trials)
            session_index += 1
            print('success')
        except:
            print('could not extract trials for date: ' + str(session) + ' continuing to next date')
    session_df = pd.concat(session_list)

    if dummies is True:
        column_names = ['Ct_Stim', 'Pt_Hit', 'Pt_Stim', 'Pt_csr', 'Pt_wr', 'PPt_stim', 'Lt_stim']
        cat_vars = ['Ct_Stim', 'Pt_Stim', 'PPt_stim']  # create dummy variables for all the stimuli
        #cat_vars = ['Ct_Stim', 'Pt_Hit', 'Pt_Stim', 'Pt_csr', 'Pt_wr', 'PPt_stim']  # dummies for everything
        for var in cat_vars:
            cat_list = 'var' + '_' + var
            cat_list = pd.get_dummies(session_df[var], prefix=var)
            data1 = session_df.join(cat_list)
            session_df = data1
        session_df_vars = session_df.columns.values.tolist()
        to_keep = [i for i in session_df_vars if i not in cat_vars]
        session_df_final=session_df[to_keep]
        session_df = session_df_final
    return session_df


# Running the logistic regression
def drop_x(df, ct_stim=False, pt_hit=False, pt_stim = False, pt_csr=False, pt_wr=False, ppt_stim=False, lt_stim=False):
    x_list = []
    params = [ct_stim, pt_hit, pt_stim, pt_csr, pt_wr, ppt_stim, lt_stim]
    param_names = ['Ct_Stim', 'Pt_Hit', 'Pt_Stim', 'Pt_csr', 'Pt_wr', 'PPt_stim', 'Lt_stim']
    index = 0
    for param in params:
        if param is False:
            x_list.append(param_names[index])
        index += 1
    if len(x_list) == 1:
        print('Only one column of x data chosen, will cause error downstream, consider adding more x data')
    x = df[x_list]
    return x


def train_data(x,y, auc=False):
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.20, random_state=0)
    logreg = LogisticRegression(penalty='l2',  # L2 regulation to avoid overfitting
                                fit_intercept=True,  # include intercept/bias in decision model
                                )

    #rfe = RFE(logreg, 20)  # don't know what the 20 means

    logreg.fit(x_train, y_train)  # look up what these values really mean
    y_pred = logreg.predict(x_test)
    cnf_matrix = metrics.confusion_matrix(y_test, y_pred)
    print("Accuracy:", metrics.accuracy_score(y_test, y_pred))
    print("Precision:", metrics.precision_score(y_test, y_pred))
    print("Recall:", metrics.recall_score(y_test, y_pred))
    parameters = logreg.coef_
    print(parameters)

    # AUC
    if auc is True:
        logit_roc_auc = roc_auc_score(y_test, y_pred)
        fpr, tpr, thresholds = roc_curve(y_test, logreg.predict_proba(x_test)[:,1])
        plt.figure()
        plt.plot(fpr, tpr, label='Logistic Regression (area = %0.2f)' %logit_roc_auc)
        plt.plot([0,1], [0, 1], 'r--')
        plt.xlim([0.0, 1.0])
        plt.ylim([0.0, 1.05])
        plt.xlabel('False Positive Rate')
        plt.ylabel('True Positive Rate')
        plt.title('Receiver operating characteristic')
        plt.legend(loc='lower right')
        plt.savefig('Log_ROC')
        plt.show()


    return cnf_matrix


def cnf_heatmap(cnf_matrix):
    fig, ax = plt.subplots()
    sns.heatmap(pd.DataFrame(cnf_matrix), annot=True, cmap="RdPu", fmt='g')
    ax.xaxis.set_label_position("top")
    plt.title('Confusion matrix', y=1.1)
    plt.ylabel('Actual label')
    plt.xlabel('Predicted label')

    return None


def test_model(df, ct_stim = False, pt_hit = False, pt_stim = False, pt_csr=False, pt_wr=False, ppt_stim=False,
               lt_stim=False):
    params = [ct_stim, pt_hit, pt_stim, pt_csr, pt_wr, ppt_stim, lt_stim]
    y = df['Ct_wr']
    x = drop_x(df, ct_stim=params[0], pt_hit=params[1], pt_stim= params[2], pt_csr=params[3], pt_wr=params[4],
               ppt_stim=params[5],lt_stim=params[6])
    cnf = train_data(x,y)
    cnf_heatmap((cnf))
    return cnf


def rfe(x,y):
    logreg = LogisticRegression()
    rfe = RFE(logreg, 7)
    rfe = rfe.fit(x, y)
    print(rfe.support_)
    print(rfe.ranking_)

    logit_model = sm.Logit(y, x)
    result = logit_model.fit()
    print(result.summary2())


def check_all_models(df):
    y = df['Ct_wr']
    cnf_list = []
    print('Testing model with all params..')
    cnf0 = test_model(df)
    cnf_list.append(cnf0)
    print('Testing model without Ct_stim..')
    cnf1 = test_model(df, ct_stim=True)
    cnf_list.append(cnf1)
    print('Testing model without Pt_hit..')
    cnf2 = test_model(df, pt_hit=True)
    cnf_list.append(cnf2)
    print('Testing model without Pt_stim..')
    cnf3 = test_model(df, pt_stim=True)
    cnf_list.append(cnf3)
    print('Testing model without pt_csr..')
    cnf4 = test_model(df, pt_csr=True)
    cnf_list.append(cnf4)
    return cnf_list


# Different logistic functions, could concatenate into one function
def cv_models_logit(df, plot=False, avoid_nan=False, normalise=True, dummies=True, solver=None):  # have not figured out in this to deal with potential dummy variables
    # should I add a way chose which model to run
    # and add animal id?
    df['intercept'] = 1  # think I need this when I only have Ct_stim to estimate intercept
    y = df['Ct_wr']
    pr2_dict = {}
    model_dict = {'A: No history':
                      ['Ct_Stim', 'intercept'],
                  'B: Correct-side history':
                      ['Ct_Stim', 'Pt_csr', 'intercept'],
                  'C: Reward history':
                      ['Ct_Stim', 'Pt_Hit', 'intercept'],
                  'D: Correct-side/Action history':
                      ['Ct_Stim', 'Pt_csr', 'Pt_wr', 'intercept'],
                  'E: Correct-side + short-term sens. history':
                      ['Ct_Stim', 'Pt_Stim','Pt_csr', 'PPt_stim', 'intercept'],
                  'F: Correct-side + short and long term sens. history':
                      ['Ct_Stim', 'Pt_Stim', 'Pt_csr', 'PPt_stim', 'Lt_stim', 'intercept'],
                  'G: Reward + short and long term sens history':
                      ['Ct_Stim', 'Pt_Hit', 'Pt_Stim', 'PPt_stim', 'Lt_stim', 'intercept'],
                  'H: Correct-side + short and long term sens. history + Preseverance':
                      ['Ct_Stim', 'Pt_Stim', 'Pt_csr', 'Pt_wr', 'PPt_stim', 'Lt_stim', 'intercept'],
                  'I: Correct-side + long term sens. history':
                      ['Ct_Stim', 'Pt_csr', 'Lt_stim', 'intercept']
                  }


    dummy_list = ['Ct_Stim', 'Pt_Stim', 'PPt_stim']

    for model in model_dict:
        if dummies is True:
            x_dummy_list = []
            x_list = model_dict[model].copy()
            #print(str(x_list))
            for column_name in model_dict[model]:
                #print(str(column_name))
                if column_name in dummy_list:
                    x_list.remove(column_name)
                    print('Removed, now' + str(x_list))
            x_without_dummies = df[x_list]
            x_dummy_list.append(x_without_dummies)
            for dummy in dummy_list:
                if dummy in model_dict[model]:
                    x_dummy = df.filter(regex='^'+dummy, axis=1)
                    x_dummy_list.append(x_dummy)
            x = pd.concat((x_dummy_list), axis=1)

        else:
            x = df[model_dict[model]]

        if normalise is True:
            x_scaled = scaler.fit_transform(x)
            x_df = pd.DataFrame(x_scaled, columns=x.columns, index=x.index)  # turn array back into df
            x_df = x_df.drop(columns=['intercept'])  # remove old intercept it gets transformed to 0
            x_df['intercept'] = 1  # add the intercept again
            x = x_df

        print('Model is: ' + str(model))
        print(model)

        # do I need to divide into train and test data sets?

        # test model
        logit_model = sm.Logit(y, x)
        if solver is not None:
            result = logit_model.fit(method=solver)
        else:
            result = logit_model.fit_regularized(alpha=1, L1_wt=0.0)
        print(result.summary2())
        #print(result.prsquared)
        p = np.isnan(result.pvalues[0])  # check if weight for Ct_stim is Nan
        if avoid_nan is True:
            index = 0
            while p == True:  # if there are nan values in the results consider re-running, this is a short term fix.
                # kind of want to make so it only effect Ct_stim, the result doesn't get negative for the others.
                print('detected null value, adding to intercept')
                x['intercept'] = x['intercept'] + 0.02
                logit_model = sm.Logit(y, x)
                result = logit_model.fit_regularized(alpha=1, L1_wt=0.0)
                p = np.isnan(result.pvalues[0])
                index += 1
                if index == 20:
                    break


        pr2_dict[str(model)] = result.prsquared  # at r2 value to dict

    if plot is True:
        pr2_df = pd.DataFrame.from_dict(pr2_dict, orient='index')
        pr2_df.plot.bar()
        plt.xticks(rotation=10)


    return pr2_dict


def cv_models_logreg(df, plot=False, normalise=True, dummies=True):  # have not figured out in this to deal with potential dummy variables
    #df['intercept'] = 1  # think I need this when I only have Ct_stim to estimate intercept
    y = df['Ct_wr']
    pr2_dict = {}
    model_dict = {'A: No history':
                      ['Ct_Stim', 'intercept'],
                  'B: Correct-side history':
                      ['Ct_Stim', 'Pt_csr', 'intercept'],
                  'C: Reward history':
                      ['Ct_Stim', 'Pt_Hit', 'intercept'],
                  'D: Correct-side/Action history':
                      ['Ct_Stim', 'Pt_csr', 'Pt_wr', 'intercept'],
                  'E: Correct-side + short-term sens. history':
                      ['Ct_Stim', 'Pt_Stim','Pt_csr', 'PPt_stim', 'intercept'],
                  'F: Correct-side + short and long term sens. history':
                      ['Ct_Stim', 'Pt_Stim', 'Pt_csr', 'PPt_stim', 'Lt_stim', 'intercept'],
                  'G: Reward + short and long term sens history':
                      ['Ct_Stim', 'Pt_Hit', 'Pt_Stim', 'PPt_stim', 'Lt_stim', 'intercept'],
                  'H: Correct-side + short and long term sens. history + Preseverance':
                      ['Ct_Stim', 'Pt_Stim', 'Pt_csr', 'Pt_wr', 'PPt_stim', 'Lt_stim', 'intercept'],
                  'I: Correct-side + long term sens. history':
                      ['Ct_Stim', 'Pt_csr', 'Lt_stim', 'intercept']
                  }
    dummy_list = ['Ct_Stim', 'Pt_Stim', 'PPt_stim']

    for model in model_dict:
        if dummies is True:
            x_dummy_list = []
            x_list = model_dict[model].copy()
            #print(str(x_list))
            for column_name in model_dict[model]:
                #print(str(column_name))
                if column_name in dummy_list:
                    x_list.remove(column_name)
                    print('Removed, now' + str(x_list))
            x_without_dummies = df[x_list]
            x_dummy_list.append(x_without_dummies)
            for dummy in dummy_list:
                if dummy in model_dict[model]:
                    x_dummy = df.filter(regex='^'+dummy, axis=1)
                    x_dummy_list.append(x_dummy)
            x = pd.concat((x_dummy_list), axis=1)

        else:
            x = df[model_dict[model]]

        #print('Model is: ' %model_dict[model])

        # do I need to divide into train and test data sets?

        # estimate intercept
        #logit_model = sm.Logit(y, x)
        #result = logit_model.fit_regularized(alpha=1, L1_wt=0.0)
        #print(result.summary2())
        #intercept_value = result.params[(len(x.columns)-1)]  # access the last column
        #print('intercept is: ' %intercept_value)
        x = x.drop(columns=['intercept'])  # drop the old intercept column, actually wht does it not complain?
        #x['Intercept'] = intercept_value

        # test model
        if normalise is True:
            x = scaler.fit_transform(x)
            # don't need to do other stuff from cv_logit to this because this automatically fits and intercept.
        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.20, random_state=0)
        clf = LogisticRegressionCV(cv=5, random_state=0, fit_intercept=True)
        clf.fit(x_train, y_train)  # look up what these values really mean
        y_pred = clf.predict(x_test)
        r2 = metrics.r2_score(y_test, y_pred)
        #print(r2)

        pr2_dict[str(model)] = r2 # at r2 value to dict

    if plot is True:
        pr2_df = pd.DataFrame.from_dict(pr2_dict, orient='index')
        pr2_df.plot.bar()
        plt.xticks(rotation=10)

    return pr2_dict


def cv_models_log(df, plot=False, normalise=True, dummies=True):  # have not figured out in this to deal with potential dummy variables
    #df['intercept'] = 1  # think I need this when I only have Ct_stim to estimate intercept
    y = df['Ct_wr']
    pr2_dict = {}
    model_dict = {'A: No history':
                      ['Ct_Stim', 'intercept'],
                  'B: Correct-side history':
                      ['Ct_Stim', 'Pt_csr', 'intercept'],
                  'C: Reward history':
                      ['Ct_Stim', 'Pt_Hit', 'intercept'],
                  'D: Correct-side/Action history':
                      ['Ct_Stim', 'Pt_csr', 'Pt_wr', 'intercept'],
                  'E: Correct-side + short-term sens. history':
                      ['Ct_Stim', 'Pt_Stim','Pt_csr', 'PPt_stim', 'intercept'],
                  'F: Correct-side + short and long term sens. history':
                      ['Ct_Stim', 'Pt_Stim', 'Pt_csr', 'PPt_stim', 'Lt_stim', 'intercept'],
                  'G: Reward + short and long term sens history':
                      ['Ct_Stim', 'Pt_Hit', 'Pt_Stim', 'PPt_stim', 'Lt_stim', 'intercept'],
                  'H: Correct-side + short and long term sens. history + Preseverance':
                      ['Ct_Stim', 'Pt_Stim', 'Pt_csr', 'Pt_wr', 'PPt_stim', 'Lt_stim', 'intercept'],
                  'I: Correct-side + long term sens. history':
                      ['Ct_Stim', 'Pt_csr', 'Lt_stim', 'intercept']
                  }
    dummy_list = ['Ct_Stim', 'Pt_Stim', 'PPt_stim']
    for model in model_dict:
        if dummies is True:
            x_dummy_list = []
            x_list = model_dict[model].copy()
            #print(str(x_list))
            for column_name in model_dict[model]:
                #print(str(column_name))
                if column_name in dummy_list:
                    x_list.remove(column_name)
                    print('Removed, now' + str(x_list))
            x_without_dummies = df[x_list]
            x_dummy_list.append(x_without_dummies)
            for dummy in dummy_list:
                if dummy in model_dict[model]:
                    x_dummy = df.filter(regex='^'+dummy, axis=1)
                    x_dummy_list.append(x_dummy)
            x = pd.concat((x_dummy_list), axis=1)

        else:
            x = df[model_dict[model]]

        #print('Model is: ' %model_dict[model])

        # do I need to divide into train and test data sets?

        # estimate intercept
        #logit_model = sm.Logit(y, x)
        #result = logit_model.fit_regularized(alpha=1, L1_wt=0.0)
        #print(result.summary2())
        #intercept_value = result.params[(len(x.columns)-1)]  # access the last column
        #print('intercept is: ' %intercept_value)
        x = x.drop(columns=['intercept'])  # drop the old intercept column
        #x['Intercept'] = intercept_value

        # test model
        if normalise is True:
            x = scaler.fit_transform(x)
        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.20, random_state=0)
        clf = LogisticRegression(random_state=0, fit_intercept=True)
        clf.fit(x_train, y_train)  # look up what these values really mean
        y_pred = clf.predict(x_test)
        r2 = metrics.r2_score(y_test, y_pred)
        #print(r2)

        pr2_dict[str(model)] = r2 # at r2 value to dict

    if plot is True:
        pr2_df = pd.DataFrame.from_dict(pr2_dict, orient='index')
        pr2_df.plot.bar()
        plt.xticks(rotation=10)

    return pr2_dict


def plot_all_logs(df, animal_id=None, avoid_nan=False, normalise=True, dummies=True):
    dict1 = cv_models_logit(df, plot=False, avoid_nan=avoid_nan, normalise=normalise, dummies=dummies)
    dict2 = cv_models_logreg(df, normalise=normalise, dummies=dummies)
    dict3 = cv_models_log(df, normalise=normalise, dummies=dummies)
    dicts = pd.DataFrame.from_dict([dict1, dict2, dict3])
    dicts.set_index([pd.Index(['Logit','LogregCV', 'Logreg' ])])
    dicts.plot.bar()

    plt.title('PseudoR2 for the different Logistic functions')
    if animal_id is not None:
        plt.title('PseudoR2 for the different Logistic functions for animal: ' + str(animal_id))
    plt.xticks(np.arange(3), ('Logit()', 'LogRegCV()', 'LogReg()'), rotation=0)
    plt.xlabel('Function used: ', fontsize=14)
    plt.ylabel('PseudoR2', fontsize=14)
    return dicts


def run_all_logplots():
    for animal in animals:
        try:
            df = all_trials(sc, animal, date_list_sc, dummies=True)
            #id = str(animal)
            fig_name = 'sc_' + animal + '_R2_nanF_normT_dum_stNR'
            plot = plot_all_logs(df, animal_id=animal, avoid_nan=False)
            plt.savefig('Rot3_data\\SoundCat\\LogReg\\' + fig_name + '.png')
            plt.close()
        except:
            print('could not extract data and test models for animal: '+ str(animal))


# create the cleaned up dataframe
sc = clean_up_df(Animal_df)  # do not want to include '2019-08-21', should remove (data is weird)
date_list = sc.index.values
animals = ['AA01', 'AA03', 'AA05', 'AA07', 'DO04', 'DO08', 'SC04', 'SC05',
           'VP01', 'VP07', 'VP08']

# chose animal and potentially data to analyze, example
animal_id = 'VP01'
date2 = '2019-08-23'
date = '2019-08-06'
# create and example df
#session_df = all_trials(sc, animal_id, date_list, dummies=False)
#df = session_df
#y = df['Ct_wr']
#x = df[['Ct_Stim', 'Pt_Hit', 'Pt_Stim', 'Pt_csr', 'Pt_wr', 'PPt_stim', 'Lt_stim']]
#x1 = ['Ct_Stim', 'Pt_Hit', 'Pt_Stim', 'Pt_csr', 'Pt_wr', 'PPt_stim',
 #      'Lt_stim', 'Ct_Stim_1.0', 'Ct_Stim_2.0', 'Ct_Stim_3.0', 'Ct_Stim_4.0',
  #     'Ct_Stim_5.0', 'Ct_Stim_6.0', 'Pt_Stim_1.0', 'Pt_Stim_2.0',
  #     'Pt_Stim_3.0', 'Pt_Stim_4.0', 'Pt_Stim_5.0', 'Pt_Stim_6.0',
   #    'PPt_stim_1.0', 'PPt_stim_2.0', 'PPt_stim_3.0', 'PPt_stim_4.0',
   #    'PPt_stim_5.0', 'PPt_stim_6.0']