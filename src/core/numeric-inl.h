// SPDX-FileCopyrightText: 2025 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

// Careful text-to-double conversion shared by the Object bindings. qpdf stores
// a real number as the token text it read, which may be something std::stod
// rejects or misreads, so every place that turns a Real into a C++ double goes
// through parse_double().

#include <cctype>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <optional>
#include <string>

#include <qpdf/QPDFObjectHandle.hh>

// Strip ASCII whitespace from both ends. PDF strings that hold numbers are
// often padded by generators that treat them as fixed-width fields.
static inline std::string trimmed(std::string const &s)
{
    char const *ws = " \t\n\r\f\v";
    auto begin = s.find_first_not_of(ws);
    if (begin == std::string::npos)
        return std::string();
    auto end = s.find_last_not_of(ws);
    return s.substr(begin, end - begin + 1);
}

// Parse the whole string as a double. Rejects empty input, trailing garbage,
// out-of-range values (ERANGE) and non-finite results, so that "inf"/"nan"
// text can never reach Python as a float or Decimal.
static inline std::optional<double> parse_double(std::string const &s)
{
    if (s.empty())
        return std::nullopt;
    // Restrict to decimal notation with optional sign and exponent, so that
    // strtod's hex-float and infinity/nan spellings are never accepted.
    for (char c : s) {
        if (!(std::isdigit(static_cast<unsigned char>(c)) || c == '+' || c == '-' ||
                c == '.' || c == 'e' || c == 'E'))
            return std::nullopt;
    }
    char const *start = s.c_str();
    char *end = nullptr;
    errno = 0;
    double value = std::strtod(start, &end);
    if (end != start + s.size())
        return std::nullopt;
    if (errno == ERANGE)
        return std::nullopt;
    if (!std::isfinite(value))
        return std::nullopt;
    return value;
}

// Value of a Real object, or nullopt if its token text is not a finite
// decimal number.
static inline std::optional<double> real_as_double(QPDFObjectHandle &h)
{
    return parse_double(trimmed(h.getRealValue()));
}
