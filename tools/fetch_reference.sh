#!/bin/sh
# Created by nc.ai 0.8.8.0 on macbook 2026-10-17 20:02:08
# Клонирует референсные проекты, из которых собраны данные и логика EDHUD.
# Нужно только для пересборки data/ (tools/vendor_data.py), для работы EDHUD не требуется.
set -eu
mkdir -p reference
cd reference
[ -d EDMarketConnector ] || git clone --depth 1 https://github.com/EDCD/EDMarketConnector
[ -d SrvSurvey ]         || git clone --depth 1 https://github.com/njthomson/SrvSurvey
[ -d EDDiscovery ]       || git clone --depth 1 https://github.com/EDDiscovery/EDDiscovery
echo "готово: $(pwd)"
