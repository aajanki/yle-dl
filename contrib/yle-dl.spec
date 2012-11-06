Name:		yle-dl
Version:	2.0.1
Release:	1%{?dist}
Summary:	Rtmpdump front-end for Yle servers
Group:		Applications/Multimedia
License:	GPLv2
URL:		http://aajanki.github.com/yle-dl/index.html
Source0:	%{name}-%{version}.tar.gz
Patch1:		Makefile.patch
BuildRoot:	%{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)
BuildArch:	noarch
Requires:	python pycryptopp rtmpdump

%description
yle-dl is a rtmpdump front-end for downloading media files from the
video streaming services of the Finnish national broadcasting company
Yle: Yle Areena (http://areena.yle.fi, http://ylex.yle.fi/ylex-areena)
and Elävä Arkisto (http://www.yle.fi/elavaarkisto/).

%prep
%setup -q
%patch1 -p1

%build

%install
rm -rf %{buildroot}
make install DESTDIR=%{buildroot} prefix=%{_prefix}

%clean
rm -rf %{buildroot}

%files
%doc README COPYING ChangeLog
%{_bindir}/*

%changelog
* Fri Oct 12 2012 Jari Karppinen <jari.p.karppinen at, gmail.com> - 2.0.1-1
- Packaged for Fedora.
