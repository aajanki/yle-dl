# OS-specific installation instructions for yle-dl

## Debian 10 (Buster)/Ubuntu 17.10

```
sudo apt-get install rtmpdump wget ffmpeg python3-dev python3-setuptools \
    python3-pip python3-pycryptodome python3-requests python3-lxml python3-socks \
    php-cli php-curl php-xml php-bcmath
sudo -H pip3 install --upgrade yle-dl
```


### Installing from source code on Debian 10/Ubuntu 17.10

```
sudo apt-get install git rtmpdump wget ffmpeg python3-dev python3-setuptools \
    python3-pycryptodome python3-requests python3-lxml python3-socks \
    php-cli php-curl php-xml php-bcmath
git clone https://github.com/aajanki/yle-dl.git
cd yle-dl
sudo -H python3 setup.py install
```


## Debian 9 (Stretch)/Ubuntu 16.04

```
sudo apt-get install rtmpdump wget ffmpeg python3-dev python3-setuptools \
    python3-pip python3-crypto python3-requests python3-lxml python3-socks \
    php-cli php-curl php-xml php-bcmath
sudo -H pip3 install --upgrade yle-dl
```

(You may get prompted to upgrade pip. However, it is not necessary to
upgrade pip for installing yle-dl.)

### Installing from source code on Debian 9/Ubuntu 16.04

```
sudo apt-get install git rtmpdump wget ffmpeg python3-dev python3-setuptools \
    python3-crypto python3-requests python3-lxml python3-socks \
    php-cli php-curl php-xml php-bcmath
git clone https://github.com/aajanki/yle-dl.git
cd yle-dl
sudo -H python3 setup.py install
```


## Debian 8 (Jessie)/Ubuntu 15.10 or older

```
sudo apt-get install rtmpdump wget libav-tools python-dev python-setuptools \
     python-pip python-crypto python-requests python-lxml python-socks \
     php5-cli php5-curl php5-mcrypt
sudo php5enmod mcrypt
sudo pip install pyOpenSSL ndg-httpsclient pyasn1
sudo pip install yle-dl
```

(You may get prompted to upgrade pip. However, it is not necessary to
upgrade pip for installing yle-dl.)

### Installing from source code on Debian 8/Ubuntu 15.10 or older

```
sudo apt-get install git rtmpdump wget libav-tools python-dev \
    python-setuptools python-crypto python-requests python-lxml python-socks \
    php5-cli php5-curl php5-mcrypt
sudo php5enmod mcrypt
git clone https://github.com/aajanki/yle-dl.git
cd yle-dl
sudo python setup.py install
```


## Mac OS X

[Install the PHP interpreter](https://secure.php.net/manual/en/install.macosx.php).

Install other dependencies:
```
brew install python
brew install wget
brew install --HEAD rtmpdump
brew install ffmpeg
```

Enable the PHP extensions by appending the following lines with the
correct paths in the [php.ini]:

[php.ini]:https://secure.php.net/manual/en/configuration.file.php

```
extension=/path/to/curl.so
```

Install yle-dl:

```
sudo pip install --upgrade yle-dl
```
