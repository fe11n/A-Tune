#!/bin/sh
# Copyright (c) 2019 Huawei Technologies Co., Ltd.
# A-Tune is licensed under the Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#     http://license.coscl.org.cn/MulanPSL
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FIT FOR A PARTICULAR
# PURPOSE.
# See the Mulan PSL v2 for more details.
# Create: 2019-10-29

MYPROF_PATH=~/.bash_tlbprof

HugePages=$(grep HugePages_Total /proc/meminfo | awk '{print $2}')
if [ "${HugePages}" = 0 ]; then
  rm -f ${MYPROF_PATH}
  echo "0" && exit 0
fi

[ -f ${MYPROF_PATH} ] && echo "1" && exit 0

echo "0"

