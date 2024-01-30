yle-dl on apuohjelma tiedostojen lataamiseen
[Yle Areenasta](https://areena.yle.fi),
[Elävästä arkistosta](https://yle.fi/aihe/elava-arkisto) ja
[Ylen uutissivustolta](https://yle.fi/).

Copyright (C) 2010-2024 Antti Ajanki, antti.ajanki@iki.fi

Ohjelmistolisenssi: GPL v3 tai myöhempi

Kotisivu: https://aajanki.github.io/yle-dl/

Lähdekoodi: https://github.com/aajanki/yle-dl

Asennusohjeet
-------------

Alla on yleiset asennusohjeet. Yksityiskohtaisemmat asennusohjeet
Debianille, Ubuntulle, Mac OS X:lle, Windowsille ja Androidille
löytyvät tiedostosta OS-install-instructions.md.

### 1. Asenna riippuvuudet:

* Python 3.7+
* ffmpeg (tekstitys toimii vain ffmpegin versiolla 4.1 tai sitä uudemmilla)

Joidenkin harvojen ohjelmien lataamiseen tarvitaan lisäksi:

* wget

### 2. Asenna yle-dl

1. [Asenna pipx](https://pypa.github.io/pipx/)
2. Asenna yle-dl kirjoittamalla: `pipx install yle-dl`

Komennolla `pipx install yle-dl[extra]` saat käyttöösi myös valinnaiset
ominaisuudet: videon metadatan tallentamisen tiedoston xattr-attribuuteiksi ja
automaattinen rajatun merkistön vaativien levyjen tunnistamisen.

Toinen vaihtoehto on asentaa lähdekoodeista. Lataa lähdekoodit ja aja
seuraava komento lähdekoodihakemistossa:

```shell
pip3 install --user .
```

Käyttö
------

```
yle-dl [valitsimet] URL
```

tai

```
yle-dl [valitsimet] -i tiedosto
```


Korvaa URL webbi-osoitteella, missä ladatavaa ohjelmaa voisi katsoa
nettiselaimen kautta. URL voi olla joko Yle Areenan tai Elävän
arkiston osoite.

Valitsimet:

* `-o filename`     Tallenna striimi nimettyyn tiedostoon
* `-i filename`     Lue käsiteltävät URLit tiedostosta, yksi URL per rivi
* `--latestepisode` Lataa viimeisimmän jakson sivulta
* `--showurl`       Tulostaa videon URL, ei lataa tiedostoa
* `--showtitle`     Tulostaa ohjelman nimen, ei lataa tiedostoa
* `--showmetadata`  Tulostaa metatietoja ohjelmasta. Katso docs/metadata.md
* `--vfat`          Tuota Windows-yhteensopivia tiedoston nimiä
* `--sublang lan`   Jätä tekstitykset lataamatta, jos lang on "none"
* `--resolution r`  Rajoita ladattavan striimin pystyresoluutiota
* `--maxbitrate br` Rajoita ladattavan striimin bittinopeutta (kB/s)
* `--postprocess c` Suorita ohjelma c onnistuneen latauksen jälkeen. Ohjelmalle c annetaan parametriksi ladatun videotiedoston nimi ja mahdollisten tekstitystiedostojen nimet.
* `--proxy uri`     Käytä HTTP(S)-proxyä. Esimerkki: --proxy localhost:8118
* `--destdir dir`   Aseta hakemisto mihin tiedostot tallennetaan
* `--pipe`          Ohjaa striimi stdout:iin, esim. "yle-dl --pipe URL | vlc -"
* `-V`, `--verbose` Tulosta enemmän tietoja latauksen etenemisestä

Luettelon mahdollisista valitsimista (englanniksi) näkee
komentamalla `yle-dl --help`.

Lataaminen SOCKS5-proxyn kautta on mahdollista käyttämällä
tsocks-ohjelmaa.


### libav:n käyttö ffmpegin sijaan

```
yle-dl --ffmpeg avconv --ffprobe avprobe ...
```


Asetustiedosto
--------------

Kahdella viivalla (--) alkavien valitsimien arvot voi asettaa myös asetustiedostossa.
Asetukset luetaan tiedostosta `~/.yledl.conf` (tai vaihtoehtoisesti `~/.config/yledl.conf`)
tai tiedostosta, jonka nimi annetaan `--config`-valitsimella. Lähdekoodien mukana tulee
esimerkkitiedosto `yledl.conf.sample`.

Asetustiedoston syntaksi: avain=arvo, avain=true.
Komentorivivalitsimet ohittavat asetustiedostossa annetut arvot, jos
sama valitsin on määritelty kummallakin tavalla.


Valmiit asennuspaketit
----------------------

Katso lista saatavilla olevista asennuspaketeista osoitteesta
https://aajanki.github.io/yle-dl/#packages


Integraatiotestien ajaminen
---------------------------

```
pytest-3
```

Jotkin testit onnistuvat vain suomalaisesta IP-osoitteesta, koska osa
Areenan videoista on saatavilla vain Suomessa. Oletuksena tällaiset
testit jätetään suorittamatta. Ajaaksesi myös nämä testit käytä
"--geoblocked"-vipua:

```
pytest-3 --geoblocked
```


Esimerkkejä
-----------

### Areena

Areenan ohjelman lataaminen automaattisesti nimettävään tiedostoon:

```
yle-dl https://areena.yle.fi/1-787136
```

Ohjelman lataaminen tiedostoon rikos_ja_rakkaus.mkv:

```
yle-dl https://areena.yle.fi/1-1907797 -o rikos_ja_rakkaus.mkv
```

Toistaminen suoraan videotoistimessa:

```
yle-dl --pipe https://areena.yle.fi/1-787136 | mpv --slang=fi -
```

Ladatun tiedoston jatkokäsitteleminen skriptillä (katso esimerkki
scripts/muxmp4-tiedostossa):

```
yle-dl --postprocess scripts/muxmp4 https://areena.yle.fi/1-1864726
```

### Suorat TV-lähetykset

```
yle-dl https://areena.yle.fi/tv/suorat/yle-tv1

yle-dl https://areena.yle.fi/tv/suorat/yle-tv2

yle-dl https://areena.yle.fi/tv/suorat/yle-teema-fem
```

Tallenna tunti (eli 3600 sekuntia) sitten TV1:llä näytettyä lähetystä:

```
yle-dl --startposition -3600 https://areena.yle.fi/tv/suorat/yle-tv1
```

### Elävä arkisto

```
yle-dl https://yle.fi/aihe/artikkeli/2010/10/28/studio-julmahuvi-roudasta-rospuuttoon
```

### Upotetut videot yle.fi-sivustolla

```
yle-dl https://yle.fi/a/74-20036911
```
