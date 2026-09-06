// SPDX-FileCopyrightText: 2025 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

// Careful text-to-double conversion shared by the Object bindings. qpdf stores
// a real number as the token text it read, which may be something std::stod
// rejects or misreads, so every place that turns a Real into a C++ double goes
// through parse_double().

#include <cctype>
#include <cmath>
#include <optional>
#include <string>
#include <version>

#if defined(__cpp_lib_to_chars) && __cpp_lib_to_chars >= 201611L
#    include <charconv>
#    include <system_error>
#else
#    include <ios>
#    include <locale>
#    include <sstream>
#endif

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
// out-of-range values and non-finite results, so that "inf"/"nan" text can
// never reach Python as a float or Decimal.
static inline std::optional<double> parse_double(std::string const &s)
{
    if (s.empty())
        return std::nullopt;
    // Restrict to decimal notation with optional sign and exponent, so that
    // hex-float and infinity/nan spellings are never accepted.
    for (char c : s) {
        if (!(std::isdigit(static_cast<unsigned char>(c)) || c == '+' || c == '-' ||
                c == '.' || c == 'e' || c == 'E'))
            return std::nullopt;
    }
    // Parse without consulting the C locale: strtod() and std::stod() follow
    // LC_NUMERIC, so under a locale whose decimal separator is ',' they would
    // stop at the '.' in "3.5" and report trailing garbage.
    double value = 0.0;
#if defined(__cpp_lib_to_chars) && __cpp_lib_to_chars >= 201611L
    // std::from_chars does not accept a leading '+', but PDF and the previous
    // strtod-based implementation do; skip it.
    char const *start = s.data() + (s[0] == '+' ? 1 : 0);
    char const *stop = s.data() + s.size();
    if (start == stop)
        return std::nullopt;
    auto result = std::from_chars(start, stop, value);
    if (result.ec == std::errc::result_out_of_range)
        return std::nullopt;
    if (result.ec != std::errc())
        return std::nullopt;
    if (result.ptr != stop)
        return std::nullopt;
#else
    std::istringstream iss(s);
    iss.imbue(std::locale::classic());
    iss >> value;
    if (iss.fail())
        return std::nullopt;
    // Reject trailing characters: the whole string must have been consumed.
    iss.peek();
    if (!iss.eof())
        return std::nullopt;
#endif
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
