# OS-specific installation instructions for yle-dl

## Debian 9 (Stretch)/Ubuntu 16.04

```
sudo apt-get install rtmpdump wget python python-setuptools python-pip \
    python-crypto python-requests python-lxml \
    php-cli php-curl php-mcrypt php-xml php-bcmath
sudo phpenmod mcrypt
sudo -H pip install yle-dl
```

(You may get prompted to upgrade pip. However, it is not necessary to
upgrade pip for installing yle-dl.)

### Installing from source code on Debian 9/Ubuntu 16.04

```
sudo apt-get install git rtmpdump wget python-dev python-setuptools \
    python-crypto python-requests python-lxml php-cli php-curl php-mcrypt \
    php-xml php-bcmath
sudo phpenmod mcrypt
git clone git@github.com:aajanki/yle-dl.git
cd yle-dl
sudo -H python setup.py install
```

## Debian 8 (Jessie)/Ubuntu 15.10 or older

```
sudo apt-get install rtmpdump wget python python-setuptools python-pip \
    python-crypto python-requests python-lxml php5-cli php5-curl php5-mcrypt
sudo php5enmod mcrypt
sudo pip install yle-dl
```

(You may get prompted to upgrade pip. However, it is not necessary to
upgrade pip for installing yle-dl.)

### Installing from source code on Debian 8/Ubuntu 15.10. or older

```
sudo apt-get install git rtmpdump wget python-dev python-setuptools \
    python-crypto python-requests python-lxml php5-cli php5-curl php5-mcrypt
sudo php5enmod mcrypt
git clone git@github.com:aajanki/yle-dl.git
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
brew install homebrew/php/php70-mcrypt
```

Enable the PHP extensions by appending the following lines with the
correct paths in the [php.ini]:

[php.ini]:https://secure.php.net/manual/en/configuration.file.php

```
extension=/path/to/curl.so
extension=/path/to/mcrypt.so
```
