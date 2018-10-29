# OS-specific installation instructions for yle-dl

## Debian 10 (Buster)/Ubuntu 17.10

```
# If you have installed a previous version globally (without the
# --user switch in the pip install command), remove the globally
# installed version first:
sudo pip uninstall yle-dl

sudo apt-get install rtmpdump wget ffmpeg python3-dev python3-setuptools \
    python3-pip python3-pycryptodome python3-requests python3-lxml \
    php-cli php-curl php-xml php-bcmath
pip3 install --user --upgrade yle-dl
```


### Installing from source code on Debian 10/Ubuntu 17.10

```
# If you have installed a previous version globally (without the
# --user switch in the pip install command), remove the globally
# installed version first:
sudo pip uninstall yle-dl

sudo apt-get install git rtmpdump wget ffmpeg python3-dev python3-setuptools \
    python3-pycryptodome python3-requests python3-lxml \
    php-cli php-curl php-xml php-bcmath
git clone https://github.com/aajanki/yle-dl.git
cd yle-dl
python3 setup.py install --user
```


## Debian 9 (Stretch)/Ubuntu 16.04

```
# If you have installed a previous version globally (without the
# --user switch in the pip install command), remove the globally
# installed version first:
sudo pip uninstall yle-dl

sudo apt-get install rtmpdump wget ffmpeg python3-dev python3-setuptools \
    python3-pip python3-crypto python3-requests python3-lxml \
    php-cli php-curl php-xml php-bcmath
pip3 install --user --upgrade yle-dl
```

(You may get prompted to upgrade pip. However, it is not necessary to
upgrade pip for installing yle-dl.)

### Installing from source code on Debian 9/Ubuntu 16.04

```
# If you have installed a previous version globally (without the
# --user switch in the pip install command), remove the globally
# installed version first:
sudo pip uninstall yle-dl

sudo apt-get install git rtmpdump wget ffmpeg python3-dev python3-setuptools \
    python3-crypto python3-requests python3-lxml \
    php-cli php-curl php-xml php-bcmath
git clone https://github.com/aajanki/yle-dl.git
cd yle-dl
python3 setup.py install --user
```


## Debian 8 (Jessie)/Ubuntu 15.10 or older

```
# If you have installed a previous version globally (without the
# --user switch in the pip install command), remove the globally
# installed version first:
sudo pip uninstall yle-dl

sudo apt-get install rtmpdump wget libav-tools python-dev python-setuptools \
     python-pip python-crypto python-requests python-lxml \
     php5-cli php5-curl php5-mcrypt
sudo php5enmod mcrypt
pip install --user pyOpenSSL ndg-httpsclient pyasn1
pip install --user --upgrade yle-dl
```

(You may get prompted to upgrade pip. However, it is not necessary to
upgrade pip for installing yle-dl.)

### Installing from source code on Debian 8/Ubuntu 15.10 or older

```
# If you have installed a previous version globally (without the
# --user switch in the pip install command), remove the globally
# installed version first:
sudo pip uninstall yle-dl

sudo apt-get install git rtmpdump wget libav-tools python-dev \
    python-setuptools python-crypto python-requests python-lxml \
    php5-cli php5-curl php5-mcrypt
sudo php5enmod mcrypt
git clone https://github.com/aajanki/yle-dl.git
cd yle-dl
python setup.py install --user
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


## Windows 10

### Python

Download the latest Python 3 release from
https://www.python.org/downloads/windows/ and install it in C:\somepath\Python.

Append the following paths to the PATH environment variable in Control
Panel > System and security > System > Advanced system settings >
Environment Variables...:
```
C:\somepath\Python\Python36
C:\somepath\Python\Python37
C:\somepath\Python\Python36\Scripts
C:\somepath\Python\Python37\Scripts
%USERPROFILE%\AppData\Roaming\Python\Python36\Scripts
%USERPROFILE%\AppData\Roaming\Python\Python37\Scripts
```

### ffmpeg

Download the binary from
https://ffmpeg.org/download.html#build-windows. Select the latest
release build (not a nightly git build), Windows 64-bit, Static.
Extract the zip in `C:\somepath\ffmpeg`.

Append `C:\somepath\ffmpeg\bin` to the PATH environment variable.

### rtmpdump

rtmpdump is needed only for radio streams.

Download the latest Windows build from
https://rtmpdump.mplayerhq.hu/download/ and extract it to
`C:\somepath\rtmpdump`.

Append `C:\somepath\rtmpdump` to the PATH environment variable.

### PHP

PHP is needed only for live TV and a small subset of streams.

Download the latest PHP 7.x.y binary (VC15 x64 Non Thread Safe) from
https://windows.php.net/download/ and install it in `C:\somepath\php`.

Create a file `C:\somepath\php\php.ini` with the following content:
```
extension_dir=C:\somepath\php\ext
extension=php_curl.dll
extension=php_openssl.dll
```

Create a new environment variable called PHPRC with the value
`C:\somepath\php\php.ini` in Control Panel > System and security > System >
Advanced system settings > Environment Variables...

Append `C:\somepath\php` to the PATH environment variable.

### wget

Download the latest wget.exe from https://eternallybored.org/misc/wget
and copy it to C:\somepath\wget.

Append `C:\somepath\wget` to the PATH environment variable.

### yle-dl

```
pip install --user --upgrade yle-dl
```

Usage:

```
yle-dl --vfat https://areena.yle.fi/...
```


## Android

Install [Termux](https://termux.com/).

Run on the Termux terminal:
```
pkg install python python-dev make clang libgmp-dev wget ffmpeg libxml2-dev libxml2-utils libxslt-dev
pip install pycryptodome lxml yle-dl
```
