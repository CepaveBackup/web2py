#!/usr/bin/env python

import time
import yaml
import docker
import requests
from os.path import expanduser
from urlparse import urlparse

# Init
_DOCKER_DEFAULT_PATH = expanduser("~") + '/.docker'
_filePath = _DOCKER_DEFAULT_PATH + '/dockmon.yml'

def readConfig(filePath=_filePath):
  with open(filePath, 'r') as f:
    return yaml.load(f)

config = readConfig()['registry']
protocol = 'https://' if config['ssl']['isHttps'] else 'http://'

@auth.requires_login()
def list():
    domainList = config['domain']

    msgList1 = []
    msgList2 = []
    hostUrl1 = protocol + domainList[0]
    hostUrl2 = protocol + domainList[1]
    form1 = _getForm(hostUrl1, _listRegistry(hostUrl1))
    form2 = _getForm(hostUrl2, _listRegistry(hostUrl2))

    # Update
    form1 = _formHandler('form_one', form1, hostUrl1, msgList1)
    form2 = _formHandler('form_two', form2, hostUrl2, msgList2)

    return dict(host1=hostUrl1, form1=form1, msg1=msgList1, host2=hostUrl2, form2=form2, msg2=msgList2)

def _formHandler(formName, form, hostUrl, msgList):
    if form.process(formname=formName).accepted:
        var = form.vars
        formData = dict(form.vars)
        for name, flag in formData.iteritems():
            if flag:
                repo, tag = name.split(':')
                msgList.append( delManifest(hostUrl, repo, tag) )

        # Update the info
        if msgList:
            form = _getForm(hostUrl, _listRegistry(hostUrl))
            form.vars = var
        response.flash = 'form accepted'
    return form

def _getContainerName(client, labelName='registry'):
    label = { 'label': labelName }
    resp = client.containers(filters=label)
    for reg in resp:
        # Remove the first character '/'
        return reg['Names'][0][1:]
    return ''

@auth.requires_login()
def gc():
    _SLEEP_TIME=0.5
    _CONFIG_PATH='/etc/docker/registry'

    f = lambda path: docker.tls.TLSConfig(
        client_cert=( path + '/cert.pem', path + '/key.pem'),
        verify= path + '/ca.pem'
    )
    cp = lambda src, dst: 'cp {0}/{1} {0}/{2}'.format(_CONFIG_PATH, src, dst)
    hostUrl = request.vars['dn']
    up = urlparse(hostUrl)
    url = '{}://{}:2376'.format(up.scheme, up.hostname)
    client = docker.Client(base_url=url, tls=f(_DOCKER_DEFAULT_PATH))
    containerName = _getContainerName(client)
    msgList = []
    if not containerName:
        msgList.append('[Err] Registry not found!')
        return dict(host=hostUrl, msgs=ms)

    # Set read-only flag before GC
    idDict = client.exec_create(containerName, cp('rcfg.yml', 'config.yml'))
    resp = client.exec_start(idDict)
    msg = '[EXEC][R] {}'.format(resp)
    msgList.append(msg)
    client.restart(containerName)
    time.sleep(_SLEEP_TIME)

    # GC
    idDict = client.exec_create(containerName, '/bin/registry garbage-collect {}/config.yml'.format(_CONFIG_PATH))
    resp = client.exec_start(idDict)
    msg = '[EXEC][GC] {}'.format(resp)
    msgList.append(msg)
    time.sleep(_SLEEP_TIME)

    # Restore read-only flag after GC
    idDict = client.exec_create(containerName, cp('wcfg.yml', 'config.yml'))
    resp = client.exec_start(idDict)
    msg = '[EXEC][W] {}'.format(resp)
    msgList.append(msg)
    client.restart(containerName)

    return dict(host=hostUrl, msgs=msgList)

def _listRegistry(hostUrl):
    repDict = {}
    repoList = _getRepos(hostUrl)
    if repoList:
        for idx, repo in enumerate(repoList):
            tagList = _getTags(hostUrl, repo)
            repDict[repo] = tagList
    return repDict

def _getForm(hostUrl, regDict):
    rowList = []
    rowList.append( TR(TH('IMAGE'), TH('DELETE')) )
    for repo, tagList in regDict.iteritems():
        if tagList is None:
            continue
        for tag in tagList:
            name = repo + ':' + tag
            rowList.append(TR(name, INPUT(_type='checkbox', _name=name)))
    rowList.append(TR('', INPUT(_type='submit', _value='SUBMIT')))
    form = FORM(TABLE(*rowList))
    form.add_button('Refresh', URL('list'))
    form.add_button('GC', URL('gc', vars=dict(dn=hostUrl)))
    return form

def _getRepos(hostUrl):
    method = requests.get
    url = hostUrl + '/v2/_catalog'
    kw = { 'url': url }

    r = _handleRequest(200, method, **kw)
    if r is not None:
        return r.json()['repositories']
    return None

def _getTags(hostUrl, repoStr):
    method = requests.get
    url = '{}/v2/{}/tags/list'.format(hostUrl, repoStr)
    kw = { 'url': url }

    r = _handleRequest(200, method, **kw)
    if r is not None:
        return r.json()['tags']
    return None

def delManifest(hostUrl, repoStr, tagStr):
    digest = getDigest(hostUrl, repoStr, tagStr)
    if digest is None:
        return None

    method = requests.delete
    url = '{}/v2/{}/manifests/{}'.format(hostUrl, repoStr, digest)
    kw = { 'url': url }

    r = _handleRequest(202, method, **kw)
    if r is not None:
        return "[DEL][{}:{}] {}".format(repoStr, tagStr, digest)
    return None

def getDigest(hostUrl, repoStr, tagStr):
    method = requests.head
    url = '{}/v2/{}/manifests/{}'.format(hostUrl, repoStr, tagStr)
    v2Headers = { 'Accept': 'application/vnd.docker.distribution.manifest.v2+json' }
    kw = { 'url': url, 'headers': v2Headers }

    r = _handleRequest(200, method, **kw)
    if r is not None:
        return r.headers['docker-content-digest']
    return None

def _handleRequest(code, requestMethod, **kwargs):
    try:
        if config['login']['isAuth']:
            _setAuth(kwargs)
        cert = config['ssl'].get('certs', None) if config['ssl']['isHttps'] else None

        r = requestMethod(verify=cert, **kwargs)
        if r.status_code == code:
            return r
        print r.status_code, r.text
    except Exception as e:
        print '[Request Error]', e
    return None

def _getAuth(domainName):
    return config['login']['auths'].get(domainName, {}).get('auth')

def _setAuth(kwDict):
    domainName = urlparse(kwDict['url']).netloc
    auth = _getAuth(domainName)
    if auth is None:
        print '[Error] No Auth data.'

    # Always assign the updated headers to kwargs
    authDict = { 'Authorization': ('Basic ' + auth) }
    headers = kwDict.get('headers', {})
    headers.update(authDict)
    kwDict['headers'] = headers