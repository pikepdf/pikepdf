// SPDX-FileCopyrightText: 2025 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

#include <pybind11/pybind11.h>

#include <sstream>
#include <string>
#include <variant>
#include <vector>

namespace py = pybind11;

// Path component: either a Name (string) or array index (int)
using PathComponent = std::variant<std::string, int>;

class NamePath {
public:
    NamePath() = default;
    explicit NamePath(std::vector<PathComponent> components);

    // Append a name component, return new NamePath
    NamePath append_name(std::string const &name) const;

    // Append an index component, return new NamePath
    NamePath append_index(int index) const;

    // Access components
    std::vector<PathComponent> const &components() const { return components_; }
    bool empty() const { return components_.empty(); } // LCOV_EXCL_LINE
    size_t size() const { return components_.size(); }

    // For error messages: format path up to position
    std::string format_path(size_t up_to) const;
    std::string format_full() const;

private:
    std::vector<PathComponent> components_;
};

void init_namepath(py::module_ &m);
