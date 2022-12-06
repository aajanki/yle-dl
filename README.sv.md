Ladda ner videor från Yle Arenan

[![Build status](https://circleci.com/gh/aajanki/yle-dl.svg?style=shield)](https://app.circleci.com/pipelines/github/aajanki/yle-dl)
[![PyPI version](https://badge.fury.io/py/yle-dl.svg)](https://badge.fury.io/py/yle-dl)

Copyright (C) 2010-2022 Antti Ajanki, antti.ajanki@iki.fi

Licens: GPL v3 or later

Hemsida: https://aajanki.github.io/yle-dl/index-en.html

Källkod: https://github.com/aajanki/yle-dl

yle-dl är ett verktyg för att ladda ner mediefiler från
[Yle Arenan](https://arenan.yle.fi), [Yle arkivet](https://svenska.yle.fi/arkivet)
och [Yle nyheter](https://svenska.yle.fi/).

# Installation

Nedan finns allmänna installationsanvisningar. Mer detaljerade
installationsanvisningar för Debian, Ubuntu, Mac OS X, Windows och Android
finns i filen OS-install-instructions.md.

## 1. Insatallera besittningar:

* Python 3.6+
* pip
* ffmpeg (undertexter fungerar endast med ffmpeg 4.1 eller senare)
* setuptools (om du installerar från källkoden)

För att ladda ner några program behövs dessutom:

* wget

## 2. Installera yle-dl

Installera sedan yle-dl antingen genom att installera python paketet (kräver
inte nerladdning av källkoden)

```
pip3 install --user --upgrade yle-dl
```

eller genom att ladda ner källkoden och köra följande kommando:

```
pip3 install --user .
```

## 3. Lägg vid behov till installationsvägen till PATH

Ifall skalet klagar på att det inte kan hitta yle-dl när du kör programmet, lägg
till installationsvägen till din $PATH:

```sh
# Endast för aktuella sessionen
export PATH=$PATH:$HOME/.local/bin

# Gör ändringen permanent. Justera vid behov om du inte använder bash
echo export PATH=$PATH:\$HOME/.local/bin >> ~/.bashrc
```


# Användning

```
yle-dl [alternativ] URL
```

eller

```
yle-dl [alternativ] -i filnamn
```

där URL är webbadressen på programmet där du vanligtvis skulle se på
videon i en webbläsare.

yle-dl alternativ:

* `-o filename`       Spara streamen till namngivna filen
* `--destdir dir`     Spara filer till en mapp
* `--latestepisode`   Ladda ner senaste avsnitten
* `--showmetadata`    Skriv ut streamens metadata [i JSON format](docs/metadata.md)

Använd kommandot `yle-dl --help` för att se alla alternativ.


## Inspelning av direkt TV sändningar

```
yle-dl https://areena.yle.fi/tv/suorat/yle-tv1

yle-dl https://areena.yle.fi/tv/suorat/yle-tv2

yle-dl https://areena.yle.fi/tv/suorat/yle-teema-fem
```

Spela in sändningen som visades för en timme (3600 sekunder) sedan:

```
yle-dl --startposition -3600 https://areena.yle.fi/tv/suorat/yle-tv1
```

## Användning av libav istället för ffmpeg

```
yle-dl --ffmpeg avconv --ffprobe avprobe ...
```

# Exempel

Spara en stream från Arenan till en fil med ett automatiskt genererat namn:
```
yle-dl https://areena.yle.fi/1-787136
```

eller samma från arkivet:

```
yle-dl https://yle.fi/aihe/artikkeli/2010/10/28/studio-julmahuvi-roudasta-rospuuttoon
```

Spara en stream till en videofil med namn video.mkv:
```
yle-dl https://areena.yle.fi/1-787136 -o video.mkv
```

Spela i mpv (eller i VLC eller i någon annan videospelare) utan att ladda ner först:

```
yle-dl --pipe https://areena.yle.fi/1-787136 | mpv --cache-secs=1000 --slang=fi -
```

Kör ett skript för att efterbehandla en nedladdad video (se exemplet efterbearbetningsskript i scripts/muxmp4):

```
yle-dl --postprocess scripts/muxmp4 https://areena.yle.fi/1-787136
```
