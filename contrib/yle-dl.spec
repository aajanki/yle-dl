Name:		yle-dl
Version:	2.0.1
Release:	1%{?dist}
Summary:	rtmpdump frontend for Yle servers
Group:		Applications/Multimedia
License:	GPLv2
URL:		http://users.tkk.fi/~aajanki/rtmpdump-yle/index.html
Source0:	%{name}-%{version}.tar.gz
Patch1:		Makefile.patch
BuildRoot:	%{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)

Requires:	python python-pycrypto rtmpdump

%description
yle-dl is a rtmpdump frontend for downloading media files from the
video streaming services of the Finnish national broadcasting company
Yle: Yle Areena (http://areena.yle.fi, http://ylex.yle.fi/ylex-areena)
and Elävä Arkisto (http://www.yle.fi/elavaarkisto/).

%prep
%setup -q
%patch1 -p1

%build

%install
rm -rf %{buildroot}
make install DESTDIR=%{buildroot} prefix=/usr

%clean
rm -rf %{buildroot}

%files
%doc README COPYING ChangeLog
%{_bindir}/*

%changelog
* Thu Oct 11 2012 Jari Karppinen <jari.p.karppinen at, gmail.com> - 2.0.1
- Packaged for Fedora.

