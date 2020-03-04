#!/bin/sh
# Copyright (c) 2020 Huawei Technologies Co., Ltd.
# A-Tune is licensed under the Mulan PSL v1.
# You can use this software according to the terms and conditions of the Mulan PSL v1.
# You may obtain a copy of Mulan PSL v1 at:
#     http://license.coscl.org.cn/MulanPSL
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v1 for more details.
# Create: 2020-02-08

command -v ifconfig >/dev/null 2>&1
ret=$?
[ $ret -ne 0 ] && echo "\033[31m command ifconfig is not exist \033[31m" && exit 1

OLD_IFS="$IFS"
IFS=" "
para=($*)
IFS="$OLD_IFS"

network=${para[0]}
value=$(ifconfig "$network" | grep -w "mtu" | awk '{print $4}')
echo "$network mtu $value"
