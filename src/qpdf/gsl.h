// SPDX-FileCopyrightText: 2015 Microsoft Corporation. All rights reserved.

// SPDX-License-Identifier: MIT

// Simplified from
// https://raw.githubusercontent.com/microsoft/GSL/master/include/gsl/util

#pragma once

#include <utility>

namespace gsl {

// final_action allows you to ensure something gets run at the end of a scope
template <class F>
class final_action {
public:
    explicit final_action(F f) noexcept : f_(std::move(f)) {}

    final_action(final_action &&other) noexcept
        : f_(std::move(other.f_)), invoke_(std::exchange(other.invoke_, false))
    {
    }

    final_action(const final_action &)            = delete;
    final_action &operator=(const final_action &) = delete;
    final_action &operator=(final_action &&)      = delete;

    ~final_action() noexcept
    {
        if (invoke_)
            f_();
    }

private:
    F f_;
    bool invoke_{true};
};

// finally() - convenience function to generate a final_action
template <class F>
final_action<F> finally(const F &f) noexcept
{
    return final_action<F>(f);
}

template <class F>
final_action<F> finally(F &&f) noexcept
{
    return final_action<F>(std::forward<F>(f));
}

} // namespace gsl
