from fabric.api import *
from fabric.operations import put, get
from fabric.contrib.files import exists
import os
import datetime
import getpass

env.hosts = env.hosts or raw_input('hostname (example.com):').split(',')
env.user = env.user or raw_input('username              :')

INSTALL_SCRIPT = "setup-web2py-nginx-uwsgi-ubuntu.sh"
now =  datetime.datetime.now()
applications = '/home/www-data/web2py/applications'

def create_user(username):
    """fab -H root@host create_user:username"""
    password = getpass.getpass(name+' password for %s> ' % username)
    run('useradd -m %s' % username)
    run('usermod --password %s %s' % (crypt.crypt(password, 'salt'), username))
    run('mkdir -p ~%s/.ssh' % username)
    run('cp /etc/sudoers /tmp/sudoers.new')
    append('/tmp/sudoers.new', '%s ALL=NOPASSWD: ALL' % username, use_sudo=True)
    run('visudo -c -f /tmp/sudoers.new')
    run('EDITOR="cp /tmp/sudoers.new" visudo')
    uncomment('~%s/.bashrc' % username, '#force_color_prompt=yes')
    local('ssh-copy-id %s' % env.hosts[0])

def install_web2py():        
    """fab -H username@host install_web2py"""
    sudo('wget https://raw.githubusercontent.com/web2py/web2py/master/scripts/%s' % INSTALL_SCRIPT)
    sudo('chmod +x %s' % INSTALL_SCRIPT)
    sudo('./'+INSTALL_SCRIPT)

def start_webserver():
    sudo('service nginx start')
    sudo('start uwsgi-emperor')
    sudo('start web2py-scheduler')

def stop_webserver():
    sudo('stop uwsgi-emperor')
    sudo('service nginx stop')
    sudo('stop web2py-scheduler')

def restart_webserver():
    stop_webserver()
    start_webserver()

def notify(appname=None):
    """fab -H username@host notify:appname"""
    appname = appname or os.path.split(os.getcwd())[-1]
    appfolder = applications+'/'+appname
    with cd(appfolder):
        sudo('echo "response.flash = \'System Going Down For Maintenance\'" > models/flash_goingdown.py')

def down(appname=None):
    """fab -H username@host down:appname"""
    appname = appname or os.path.split(os.getcwd())[-1]
    appfolder = applications+'/'+appname
    with cd(appfolder):
        sudo('echo `date` > DISABLED')
        sudo('rm -rf sessions/* || true')

def up(appname=None):
    """fab -H username@host up:appname"""
    appname = appname or os.path.split(os.getcwd())[-1]
    appfolder = applications+'/'+appname
    with cd(appfolder):
        if exists('modules/flash_goingdown.py'):
            sudo('rm modules/flash_goingdown.py')
        sudo('rm DISABLED')

def mkdir_or_backup(appname):
    appfolder = applications+'/'+appname
    if not exists(appfolder):
        sudo('mkdir %s' % appfolder)
        sudo('chown -R www-data:www-data %s' % appfolder)
        backup = None
    else:
        dt = now.strftime('%y-%m-%d-%h-%m')
        backup = '%s.%s.zip' % (appname, dt)
        with cd(applications):
            sudo('zip -r %s %s' % (backup, appname))
    return backup

def git_deploy(appname, repo):
    """fab -H username@host git_deploy:appname,username/remoname"""
    appfolder = applications+'/'+appname
    backup = mkdir_or_backup(appfolder)

    if exists(appfolder):
        with cd(appfolder):
            sudo('git pull origin master')
            sudo('chown -R www-data:www-data *')
    else:
        with cd(applications):
            sudo('git clone git@github.com/%s %s' % (repo, name))
            sudo('chown -R www-data:www-data %s' % name)
    
def retrieve(appname=None):
    """fab -H username@host retrieve:appname"""
    appname = appname or os.path.split(os.getcwd())[-1]
    appfolder = applications+'/'+appname
    filename = '%s.zip' % appname
    with cd(appfolder):
        sudo('zip -r /tmp/%s *' % filename)
    get('/tmp/%s' % filename, filename)
    sudo('rm /tmp/%s' % filename)
    local('unzip %s' % filename)
    local('rm %s' % filename)

def deploy(appname=None, all=False):
    """fab -H username@host deploy:appname,all"""
    appname = appname or os.path.split(os.getcwd())[-1]
    appfolder = applications+'/'+appname
    if os.path.exists('_update.zip'):
        os.unlink('_update.zip')

    backup = mkdir_or_backup(appfolder)
            
    if all=='all' or not backup:
        local('zip -r _update.zip * -x *~ -x .* -x \#* -x *.bak -x *.bak2')
    else:        
        local('zip -r _update.zip */*.py views/*.html views/*/*.html static/*')
    put('_update.zip','/tmp/_update.zip')

    with cd(appfolder):
        sudo('unzip -o /tmp/_update.zip')
        sudo('chown -R www-data:www-data *')
        sudo('echo "%s" > DATE_DEPLOYMENT' % now)
               
    if backup:
        print 'TO RESTORE: fab restore:%s' % backup
             
def restore(backup):
    """fab -H username@host restore:backupfilename"""
    appname = backup.split('/')[-1].split('.')[0]
    appfolder = applications + '/' + appname
    with cd(appfolder):
        sudo('rm -r *')
    with cd(applications):
        sudo('unzip %s' % backup)
        sudo('chown -R www-data:www-data %s' % appname)

def cleanup(appname):
    appname = appname or os.path.split(os.getcwd())[-1]
    appfolder = applications + '/' + appname
    with cd(appfolder):
        sudo('rm -rf sessions/* || true')
        sudo('rm -rf errors/* || true')
        sudo('rm -rf cache/* || true')