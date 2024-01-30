Ladda ner videor från Yle Arenan

[![Build status](https://circleci.com/gh/aajanki/yle-dl.svg?style=shield)](https://app.circleci.com/pipelines/github/aajanki/yle-dl)
[![PyPI version](https://badge.fury.io/py/yle-dl.svg)](https://badge.fury.io/py/yle-dl)

Copyright (C) 2010-2024 Antti Ajanki, antti.ajanki@iki.fi

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

* Python 3.7+
* ffmpeg (undertexter fungerar endast med ffmpeg 4.1 eller senare)

För att ladda ner några program behövs dessutom:

* wget

## 2. Installera yle-dl

1. [Installera pipx](https://pypa.github.io/pipx/)
2. Installera yle-dl: `pipx install yle-dl`

Kommandot `pipx install yle-dl[extra]` aktiverade alla optinalfunktioner.

Ett annat alternativ är att installera från källkoden. Ladda ner
källkoden och kör följande kommando:

```shell
pip3 install --user .
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

## Konfigurationfil

Argument kan också anges i en konfigurationsfil. Standardkonfigurationsfilen är
`~/.yledl.conf` (eller alternativt `~/.config/yledl.conf`). En konfigurationsfil
kan anges via --config. Filen yledl.conf.sample innehåller ett exempel på
konfiguration.

## Användning av libav istället för ffmpeg

```
yle-dl --ffmpeg avconv --ffprobe avprobe ...
```

# Exempel

### Arenan

Spara en stream från Arenan till en fil med ett automatiskt genererat namn:
```
yle-dl https://areena.yle.fi/1-787136
```

Spara en stream till en videofil med namn video.mkv:
```
yle-dl https://areena.yle.fi/1-787136 -o video.mkv
```

Spela i mpv (eller i VLC eller i någon annan videospelare) utan att ladda ner först:

```
yle-dl --pipe https://areena.yle.fi/1-787136 | mpv --slang=fi -
```

Kör ett skript för att efterbehandla en nedladdad video (se exemplet efterbearbetningsskript i scripts/muxmp4):

```
yle-dl --postprocess scripts/muxmp4 https://areena.yle.fi/1-787136
```

### Inspelning av direkt TV sändningar

```
yle-dl https://areena.yle.fi/tv/suorat/yle-tv1

yle-dl https://areena.yle.fi/tv/suorat/yle-tv2

yle-dl https://areena.yle.fi/tv/suorat/yle-teema-fem
```

Spela in sändningen som visades för en timme (3600 sekunder) sedan:

```
yle-dl --startposition -3600 https://areena.yle.fi/tv/suorat/yle-tv1
```

### Arkivet

```
yle-dl https://yle.fi/aihe/artikkeli/2010/10/28/studio-julmahuvi-roudasta-rospuuttoon
```

### Videor på nyhetsartiklar från yle.fi

```
yle-dl https://yle.fi/a/74-20036911
```
