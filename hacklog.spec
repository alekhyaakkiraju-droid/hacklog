%global include_tests 0

Name:    hacklog
Version: 0.0.5
Release: 1%{?dist}
Summary: Hacklog Security Scoring Daemon

License: GPLv3
URL:     https://github.com/dandb/hacklog/
Source0: https://github.com/dandb/%{name}/archive/%{name}-%{version}.tar.gz

BuildArch: noarch

# ── Build requirements ────────────────────────────────────────────────────────
BuildRequires: python3 >= 3.12
BuildRequires: python3-pip
BuildRequires: python3-hatchling

# ── Runtime requirements (mirrors pyproject.toml dependencies) ───────────────
Requires: python3 >= 3.12
Requires: python3-sqlalchemy >= 2.0
Requires: python3-alembic >= 1.13
Requires: python3-pydantic-settings
Requires: python3-aiosmtplib
Requires: python3-structlog
Requires: python3-pyyaml >= 6.0
Requires: python3-prometheus_client >= 0.20

# ── Systemd integration ───────────────────────────────────────────────────────
Requires(post):   systemd
Requires(preun):  systemd
Requires(postun): systemd

%description
Hacklog is a syslog-based user behaviour analytics daemon that ingests SSH
authentication events, builds per-user behavioural profiles, calculates
weighted anomaly risk scores, and sends email alerts when scores exceed
configurable thresholds.

Originally created during Q4 2013 hackweek at Dun & Bradstreet Credibility Corp.


%prep
%setup -c

%build
# pyproject.toml / hatchling-based build; no compilation step required.

%install
rm -rf %{buildroot}
cd %{_builddir}/%{name}-%{version}/%{name}-%{version}

# Install the package into the build root using pip in isolated mode so the
# hatchling build backend from the source tree is used without touching the
# system Python environment.
pip install --no-build-isolation --no-deps \
    --root %{buildroot} \
    --prefix %{_prefix} \
    .

# Configuration directory and environment template
mkdir -p %{buildroot}%{_sysconfdir}/%{name}
install -p -m 0640 deploy/hacklog.env.example \
    %{buildroot}%{_sysconfdir}/%{name}/hacklog.env.example

# Systemd service unit
mkdir -p %{buildroot}%{_unitdir}
install -p -m 0644 deploy/hacklog.service \
    %{buildroot}%{_unitdir}/%{name}.service

# Tests are intentionally not run during RPM build (include_tests=0).
# Run the test suite via CI: python3 -m pytest tests/
%if 0%{?include_tests}
%check
cd %{_builddir}/%{name}-%{version}/%{name}-%{version}
python3 -m pytest tests/
%endif

%clean
rm -rf %{buildroot}

%post
%systemd_post %{name}.service

%preun
%systemd_preun %{name}.service

%postun
%systemd_postun_with_restart %{name}.service

%files
%license LICENSE
%doc README.md CHANGES
%{python3_sitelib}/%{name}/
%{python3_sitelib}/%{name}-%{version}.dist-info/
%{_unitdir}/%{name}.service
%config(noreplace) %{_sysconfdir}/%{name}/hacklog.env.example

%changelog
* Thu Aug 07 2026 Forge Coding Agent <forge@dandb.com> - 0.0.5-1
- Modernize spec for Python 3.12 and pyproject.toml/hatchling build system
- Replace setup.py install with pip install --no-build-isolation
- Remove all Python 2.6 compatibility blocks and distutils references
- Update BuildRequires and Requires to Python 3 packages matching pyproject.toml
- Switch from SysV init.d script to systemd service unit (deploy/hacklog.service)
- Use systemd RPM macros (%%systemd_post, %%systemd_preun, %%systemd_postun_with_restart)
- Tests disabled at build time (include_tests=0); run via CI instead
- Switch %%files to use %%{python3_sitelib} and PEP 660 dist-info directory
* Thu Oct 10 2013 Konstantin Antselovich <kantselovich@dandb.com> - 0.1.0-1
- First version of hacklog spec file 0.1.0
