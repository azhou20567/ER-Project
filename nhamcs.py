import pandas as pd
import zipfile
from io import BytesIO
import requests
from os import path, remove

# This downloads zip file for SPSS
def get_spss(url,save_loc='.',convert_cat=False):
    ext = url[-3:]
    res = requests.get(url)
    if ext == 'zip':
        zf = zipfile.ZipFile(BytesIO(res.content))
        spssf = zf.filelist[0].filename
        zz = zf.open(spssf)
        zs = zz.read()
    else:
        zs = BytesIO(res.content)
        spssf = path.basename(url)
    sl = path.join('.',spssf)
    with open(sl, "wb") as sav:
        sav.write(zs)
    df = pd.read_spss(sl,convert_categoricals=convert_cat)
    remove(sl)
    return df

# creating urls
base_url = 'https://ftp.cdc.gov/pub/health_statistics/nchs/dataset_documentation/NHAMCS/spss/'
#files = ['ed02-spss.zip',
         # 'ed03-spss.zip',
         # 'ed04-spss.zip',
         # 'ed05-sps.zip',
         # 'ed06-spss.zip',
         # 'ed07-spss.zip',
         # 'ed08-spss.zip',
         # 'ed09-spss.zip',
         # 'ed2010-spss.zip',
         # 'ed2011-spss.zip',
         # 'ed2012-spss.zip',
         # 'ed2013-spss.zip',
         # 'ed2014-spss.zip',
         # 'ed2015-spss.zip',
         # 'ed2016-spss.zip',
         # 'ed2017-spss.zip',
         # 'ed2018-spss.zip',
         # 'ed2019-spss.zip',
         # 'ed2020-spss.zip',
         # 'ed2021-spss.zip',
         # 'ed2022-spss.zip']
files = ['ed2022-spss.zip']
urls = [base_url + f for f in files]

def get_data():
    res_data = []
    for i, u in enumerate(urls):
        res_data.append(get_spss(u))
        print(f"{1+i} Downloaded")
    for r in res_data:
        r.columns = [v.upper() for v in list(r)]
    vars = []
    for i,d in enumerate(res_data):
        year = i + 2001
        vars += list(d)
    vars = list(set(vars))
    vars.sort()
    vars = pd.DataFrame(vars,columns=['V'])
    for i,d in enumerate(res_data):
        year = i + 2001
        uc = [v.upper() for v in list(d)]
        vars[str(year)] = 1*vars['V'].isin(uc)
    return res_data, vars

rd, va = get_data()
all_data = pd.concat(rd,axis=0,ignore_index=True)
all_data.to_csv('nhamcs2022.csv',index=False)
print(all_data.head())