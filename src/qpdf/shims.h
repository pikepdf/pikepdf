/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#if __cplusplus < 201402L  // If C++11

#include <memory>
#include <type_traits>
#include <utility>
#include <string>

namespace std {
    // Provide make_unique for C++11 (not array-capable)
    // See https://stackoverflow.com/questions/17902405/how-to-implement-make-unique-function-in-c11/17902439#17902439 for full version if needed
    template<typename T, typename ...Args>
    unique_ptr<T> make_unique( Args&& ...args )
    {
        return unique_ptr<T>( new T( std::forward<Args>(args)... ) );
    }

    // Provide basic std::quoted for C++11
    string quoted(const char* s);
    string quoted(const string &s);
};

#endif // }}
