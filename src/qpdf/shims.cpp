/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

/* Support for features missing from C++11, minimal versions */

#if __cplusplus < 201402L  // If C++11

#include <string>
#include <sstream>

#include "pikepdf.h"

namespace std {

string quoted(const string &s)
{
    stringstream ss;
    ss << '"';
    for (const char &c : s) {
        if (c == '"') {
            ss << "\\\"";
        } else if (c == '\\') {
            ss << "\\\\";
        } else {
            ss << c;
        }
    }
    ss << '"';
    return ss.str();
}

string quoted(const char* s)
{
    return quoted(string(s));
}


};

#endif // End C++11