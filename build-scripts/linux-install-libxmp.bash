# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# CentOS 7 does not provide libxmp for i686; only install for x86_64
if [[ $(uname -p) == 'x86_64' ]]; then
    yum install -y libxmp
fi