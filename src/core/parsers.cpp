// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "parsers.h"
#include "pikepdf.h"

#include <cmath>
#include <locale>
#include <optional>
#include <sstream>
#include <string_view>
#include <unordered_map>

#include <nanobind/stl/optional.h>

#include "numeric-inl.h"

void PyParserCallbacks::handleObject(QPDFObjectHandle obj, size_t offset, size_t length)
{
    NB_OVERRIDE_NAME("handle_object", handleObject, obj, offset, length);
}

void PyParserCallbacks::handleEOF()
{
    NB_OVERRIDE_PURE_NAME("handle_eof", handleEOF);
}

void check_operand(QPDFObjectHandle obj)
{
    switch (obj.getTypeCode()) {
    case qpdf_object_type_e::ot_null:
    case qpdf_object_type_e::ot_boolean:
    case qpdf_object_type_e::ot_integer:
    case qpdf_object_type_e::ot_real:
    case qpdf_object_type_e::ot_name:
    case qpdf_object_type_e::ot_string:
    case qpdf_object_type_e::ot_inlineimage:
        break;
    case qpdf_object_type_e::ot_array: {
        if (obj.isIndirect()) {
            throw py::type_error(
                "Indirect arrays are not allowed in content stream instructions");
        }
        for (auto &inner : obj.aitems()) {
            check_operand(inner);
        }
        break;
    }
    case qpdf_object_type_e::ot_dictionary: {
        if (obj.isIndirect()) {
            throw py::type_error(
                "Indirect dictionaries are not allowed in content stream instructions");
        }
        for (auto &kv : obj.ditems()) {
            check_operand(kv.second);
        }
        break;
    }
    default: {
        throw py::type_error("Only scalar types, arrays, and dictionaries are allowed "
                             "in content streams.");
    }
    }
}

void check_objects_in_operands(std::vector<QPDFObjectHandle> &operands)
{
    for (QPDFObjectHandle &obj : operands) {
        check_operand(obj);
    }
}

ContentStreamInstruction::ContentStreamInstruction(
    ObjectList operands, QPDFObjectHandle operator_)
    : operands(operands), operator_(operator_)
{
    if (!this->operator_.isOperator())
        throw py::type_error("operator parameter must be a pikepdf.Operator");
    check_objects_in_operands(this->operands);
}

void append_unparsed(std::string &out, ContentStreamInstruction &csi)
{
    for (QPDFObjectHandle &obj : csi.operands) {
        out += obj.unparse();
        out += ' ';
    }
    out += csi.operator_.unparse();
}

py::object ContentStreamInlineImage::get_inline_image() const
{
    auto PdfInlineImage = py::module_::import_("pikepdf").attr("PdfInlineImage");
    auto kwargs = py::dict();
    kwargs["image_data"] = this->image_data;
    kwargs["image_object"] = this->image_metadata;
    if (this->resources.isInitialized() && !this->resources.isNull())
        kwargs["resources"] = this->resources;
    auto iimage = PdfInlineImage(**kwargs);
    return iimage;
}

py::list ContentStreamInlineImage::get_operands() const
{
    auto list = py::list();
    list.append(this->get_inline_image());
    return list;
}

QPDFObjectHandle ContentStreamInlineImage::get_operator() const
{
    return QPDFObjectHandle::newOperator("INLINE IMAGE");
}

void append_unparsed(std::string &out, ContentStreamInlineImage &csii)
{
    py::bytes ii_bytes =
        py::borrow<py::bytes>(csii.get_inline_image().attr("unparse")());

    out += to_string(ii_bytes);
}

OperandGrouper::OperandGrouper(const std::string &operators, QPDFObjectHandle resources)
    : parsing_inline_image(false), count(0), resources(resources)
{
    std::istringstream f(operators);
    f.imbue(std::locale::classic());
    std::string s;
    while (std::getline(f, s, ' ')) {
        this->whitelist.insert(s);
    }
}

void OperandGrouper::handleObject(QPDFObjectHandle obj)
{
    this->count++;
    if (obj.getTypeCode() == qpdf_object_type_e::ot_operator) {
        std::string op = obj.getOperatorValue();

        // If we have a whitelist and this operator is not on the whitelist,
        // discard it and all the tokens we collected
        if (!this->whitelist.empty()) {
            if (op[0] == 'q' || op[0] == 'Q') {
                // We have token with multiple stack push/pops
                if (this->whitelist.count("q") == 0 &&
                    this->whitelist.count("Q") == 0) {
                    this->tokens.clear();
                    return;
                }
            } else if (this->whitelist.count(op) == 0) {
                this->tokens.clear();
                return;
            }
        }
        if (op == "BI") {
            this->parsing_inline_image = true;
        } else if (this->parsing_inline_image) {
            if (op == "ID") {
                this->inline_metadata = this->tokens;
            } else if (op == "EI") {
                ContentStreamInlineImage csii(
                    this->inline_metadata, this->tokens[0], this->resources);
                this->instructions.append(csii);
                this->inline_metadata = ObjectList();
                this->parsing_inline_image = false;
            }
        } else {
            ContentStreamInstruction csi(this->tokens, obj);
            this->instructions.append(csi);
        }
        this->tokens.clear();
    } else {
        this->tokens.push_back(obj);
    }
}

void OperandGrouper::handleEOF()
{
    if (!this->tokens.empty())
        this->warning = "Unexpected end of stream";
}

py::list OperandGrouper::getInstructions() const
{
    return this->instructions;
}
std::string OperandGrouper::getWarning() const
{
    return this->warning;
}

py::bytes unparse_content_stream(py::iterable contentstream)
{
    uint n = 0;
    std::string out;
    const char *delim = "";

    for (const auto &item : contentstream) {
        // First iteration: print nothing
        // All others: print "\n" to delimit previous
        // Result is no leading or trailing delimiter
        out += delim;
        delim = "\n";

        if (py::isinstance<ContentStreamInstruction>(item)) {
            auto &csi = py::cast<ContentStreamInstruction &>(item);
            append_unparsed(out, csi);
            continue;
        }

        if (py::isinstance<ContentStreamInlineImage>(item)) {
            auto &csii = py::cast<ContentStreamInlineImage &>(item);
            append_unparsed(out, csii);
            continue;
        }

        // Fallback: instruction is some combination of Python iterables.
        // Destructure and convert to C++ types. Use py::object so we accept
        // both lists and tuples (and any sequence with __getitem__).
        py::object operands_op = py::borrow<py::object>(item);
        Py_ssize_t op_size = PyObject_Length(operands_op.ptr());
        if (op_size < 0) {
            throw py::python_error();
        }

        if ((size_t)op_size != 2) {
            throw py::value_error(
                ("Wrong number of operands at content stream instruction " +
                    std::to_string(n) + "; expected 2")
                    .c_str());
        }

        auto operator_ = operands_op[1];

        QPDFObjectHandle op;
        if (py::isinstance<py::str>(operator_)) {
            auto s = py::cast<std::string>(operator_);
            op = QPDFObjectHandle::newOperator(s.c_str());
        } else if (py::isinstance<py::bytes>(operator_)) {
            auto s = to_string(operator_);
            op = QPDFObjectHandle::newOperator(s.c_str());
        } else {
            op = py::cast<QPDFObjectHandle>(operator_);
            if (!op.isOperator()) {
                throw py::type_error(
                    ("At content stream instruction " + std::to_string(n) +
                        ", the operator is not of type pikepdf.Operator, bytes "
                        "or str")
                        .c_str());
            }
        }

        if (op.getOperatorValue() == std::string("INLINE IMAGE")) {
            py::object operands_obj = py::borrow<py::object>(operands_op[0]);
            py::object iimage =
                py::borrow<py::object>(operands_obj.attr("__getitem__")(0));
            py::handle PdfInlineImage =
                py::module_::import_("pikepdf").attr("PdfInlineImage");
            if (!py::isinstance(iimage, PdfInlineImage)) {
                throw py::value_error(
                    ("Expected PdfInlineImage as operand for instruction " +
                        std::to_string(n))
                        .c_str());
            }
            py::bytes iimage_unparsed_bytes =
                py::borrow<py::bytes>(iimage.attr("unparse")());
            out += to_string(iimage_unparsed_bytes);
        } else {
            py::object operands_obj = py::borrow<py::object>(operands_op[0]);
            for (auto operand : operands_obj) {
                QPDFObjectHandle obj = objecthandle_encode(operand);
                out += obj.unparse();
                out += ' ';
            }
            out += op.unparse();
        }

        n++;
    }
    return py::bytes(out.data(), out.size());
}

// ---------------------------------------------------------------------------
// Content stream checks for pikepdf.pdfa
// ---------------------------------------------------------------------------

// The implementation limits of PDF/A that content stream operands must respect
// (pikepdf.pdfa._limits). The checks here are conservative: an operand they
// cannot show is within every limit is handed to Python, which decides and
// words the finding.
struct OperandLimits {
    long long min_integer;
    long long max_integer;
    double max_real;
    double min_real; // 0 if there is no lower limit on nonzero reals
    size_t max_string;
    size_t max_name;
    std::optional<size_t> max_array;
    std::optional<size_t> max_dict;
    int max_nesting;

    // A real is compared through its double value, with a margin wide enough
    // for any rounding in converting the token text.
    bool real_within(std::string const &text) const
    {
        auto value = parse_double(trimmed(text));
        if (!value)
            return false; // not a finite double: let Python compare it exactly
        double magnitude = std::fabs(*value);
        if (magnitude >= this->max_real * (1.0 - 1e-9))
            return false;
        if (this->min_real > 0.0) {
            if (magnitude == 0.0)
                return text.find_first_of("123456789") == std::string::npos;
            if (magnitude <= this->min_real * (1.0 + 1e-9))
                return false;
        }
        return true;
    }

    bool within(QPDFObjectHandle &obj, int depth) const
    {
        if (depth > this->max_nesting)
            return false;
        switch (obj.getTypeCode()) {
        case qpdf_object_type_e::ot_null:
        case qpdf_object_type_e::ot_boolean:
            return true;
        case qpdf_object_type_e::ot_integer: {
            auto value = obj.getIntValue();
            return this->min_integer <= value && value <= this->max_integer;
        }
        case qpdf_object_type_e::ot_real:
            return this->real_within(obj.getRealValue());
        case qpdf_object_type_e::ot_string:
            return obj.getStringValue().size() <= this->max_string;
        case qpdf_object_type_e::ot_name:
            return obj.getName().size() - 1 <= this->max_name;
        case qpdf_object_type_e::ot_array: {
            if (obj.isIndirect())
                return false;
            if (this->max_array && obj.getArrayNItems() > (int)*this->max_array)
                return false;
            for (auto &item : obj.aitems()) {
                if (!this->within(item, depth + 1))
                    return false;
            }
            return true;
        }
        case qpdf_object_type_e::ot_dictionary: {
            if (obj.isIndirect())
                return false;
            // The entries Python's items() gives, including null values
            auto entries = obj.getDictAsMap();
            if (this->max_dict && entries.size() > *this->max_dict)
                return false;
            for (auto &[key, value] : entries) {
                if (key.size() - 1 > this->max_name)
                    return false;
                if (!this->within(value, depth + 1))
                    return false;
            }
            return true;
        }
        default:
            return false;
        }
    }
};

static py::str latin1_str(std::string const &s)
{
    PyObject *str = PyUnicode_DecodeLatin1(s.data(), (Py_ssize_t)s.size(), nullptr);
    if (!str)
        throw py::python_error();
    return py::steal<py::str>(str);
}

// Operand signatures of pikepdf.pdfa._content.OPERATORS: n number, i
// integer, N name, s string, a array, D dictionary or name.
static bool operand_matches(char kind, QPDFObjectHandle &operand)
{
    switch (kind) {
    case 'n':
        return operand.isInteger() || operand.isReal();
    case 'i':
        return operand.isInteger();
    case 'N':
        return operand.isName();
    case 's':
        return operand.isString();
    case 'a':
        return operand.isArray();
    case 'D':
        return operand.isName() || operand.isDictionary();
    default:
        return false;
    }
}

static bool operands_match(std::string const &signature, ObjectList &operands)
{
    if (operands.size() != signature.size())
        return false;
    for (size_t i = 0; i < signature.size(); i++) {
        if (!operand_matches(signature[i], operands[i]))
            return false;
    }
    return true;
}

// The operator table and limits that pikepdf.pdfa checks content with; see
// the _ContentChecker stub for the events that check() returns.
class ContentChecker {
public:
    struct Operator {
        std::string signature;
        py::str name;
        // Whether a handler exists, and whether it reads the operands
        bool handled = false;
        bool handler_reads_operands = false;
    };

    ContentChecker(py::dict operators, py::dict handlers, OperandLimits limits)
        : limits(limits)
    {
        for (auto [key, value] : operators) {
            auto name = py::borrow<py::str>(key);
            this->operators[py::cast<std::string>(name)] =
                Operator{py::cast<std::string>(value), name};
        }
        for (auto [key, value] : handlers) {
            auto it = this->operators.find(py::cast<std::string>(key));
            if (it == this->operators.end())
                throw py::value_error("handler for an operator not in the table");
            it->second.handled = true;
            it->second.handler_reads_operands = py::cast<bool>(value);
        }
    }

    std::pair<py::list, size_t> check(QPDFObjectHandle &stream) const;

    std::unordered_map<std::string, Operator> operators;
    OperandLimits limits;
};

// Groups a content stream into instructions exactly as OperandGrouper does
// (so parse errors and warnings are the same as parse_content_stream's), and
// checks each instruction as it is completed.
class ContentCheckCallbacks : public QPDFObjectHandle::ParserCallbacks {
public:
    ContentCheckCallbacks(ContentChecker const &checker, QPDFObjectHandle resources)
        : checker(checker), resources(resources)
    {
    }

    void handleObject(QPDFObjectHandle obj) override
    {
        if (obj.getTypeCode() != qpdf_object_type_e::ot_operator) {
            this->tokens.push_back(obj);
            return;
        }
        std::string op = obj.getOperatorValue();
        if (op == "BI") {
            this->parsing_inline_image = true;
        } else if (this->parsing_inline_image) {
            if (op == "ID") {
                this->inline_metadata = this->tokens;
            } else if (op == "EI") {
                ContentStreamInlineImage csii(
                    this->inline_metadata, this->tokens.at(0), this->resources);
                this->events.append(
                    py::make_tuple("inline", this->count, py::cast(std::move(csii))));
                this->count++;
                this->inline_metadata = ObjectList();
                this->parsing_inline_image = false;
            }
        } else {
            check_objects_in_operands(this->tokens);
            this->check_instruction(op);
            this->count++;
        }
        this->tokens.clear();
    }

    void handleEOF() override
    {
        if (!this->tokens.empty())
            this->warning = "Unexpected end of stream";
    }

    py::list events;
    size_t count = 0;
    std::string warning;

private:
    py::list operand_list() const
    {
        py::list operands;
        for (auto const &operand : this->tokens)
            operands.append(py::cast(operand));
        return operands;
    }

    void check_instruction(std::string const &op)
    {
        for (auto &operand : this->tokens) {
            if (!this->checker.limits.within(operand, 0))
                this->events.append(
                    py::make_tuple("limits", this->count, py::cast(operand)));
        }
        auto it = this->checker.operators.find(op);
        if (it == this->checker.operators.end()) {
            this->events.append(
                py::make_tuple("undefined", this->count, latin1_str(op)));
            return;
        }
        auto const &entry = it->second;
        if (entry.signature != "*" && !operands_match(entry.signature, this->tokens)) {
            this->events.append(py::make_tuple(
                "operands", this->count, entry.name, this->operand_list()));
            return;
        }
        if (entry.handled) {
            this->events.append(py::make_tuple("op",
                this->count,
                entry.name,
                entry.handler_reads_operands ? this->operand_list() : py::list()));
        }
    }

    ContentChecker const &checker;
    QPDFObjectHandle resources;
    ObjectList tokens;
    bool parsing_inline_image = false;
    ObjectList inline_metadata;
};

std::pair<py::list, size_t> ContentChecker::check(QPDFObjectHandle &stream) const
{
    QPDFObjectHandle resources;
    if (stream.isStream())
        resources = stream.getDict().getKey("/Resources");
    ContentCheckCallbacks callbacks(*this, resources);
    QPDFObjectHandle::parseContentStream(stream, &callbacks);
    if (!callbacks.warning.empty())
        python_warning(callbacks.warning.c_str());
    return {callbacks.events, callbacks.count};
}

// Port of the raw content scan of pikepdf.pdfa: see the _scan_raw_content
// stub. Tokenizes just enough to find hex strings, skipping literal strings,
// comments and inline image data.
static constexpr std::string_view RAW_WHITESPACE{"\0\t\n\x0c\r ", 6};

static bool is_raw_whitespace(char c)
{
    return RAW_WHITESPACE.find(c) != std::string_view::npos;
}

static size_t skip_literal_string(std::string_view data, size_t pos)
{
    int depth = 0;
    while (pos < data.size()) {
        char c = data[pos++];
        if (c == '\\') {
            pos++;
        } else if (c == '(') {
            depth++;
        } else if (c == ')') {
            if (--depth == 0)
                return pos;
        }
    }
    return data.size();
}

static char const *hex_string_problem(std::string_view body)
{
    size_t digits = 0;
    for (char c : body) {
        if (is_raw_whitespace(c))
            continue;
        if (!std::isxdigit(static_cast<unsigned char>(c)))
            return "6.1.6-2";
        digits++;
    }
    return digits % 2 ? "6.1.6-1" : nullptr;
}

static bool starts_inline_image_data(std::string_view data, size_t pos)
{
    if (data.compare(pos, 2, "ID") != 0)
        return false;
    if (pos > 0) {
        char before = data[pos - 1];
        if (!is_raw_whitespace(before) &&
            std::string_view(")]>}").find(before) == std::string_view::npos)
            return false;
    }
    return pos + 2 == data.size() || is_raw_whitespace(data[pos + 2]);
}

static py::list scan_raw_content(py::bytes data_bytes, std::vector<py::bytes> images)
{
    std::string_view data(data_bytes.c_str(), data_bytes.size());
    py::list problems;
    size_t image = 0;
    size_t pos = 0;
    while (pos < data.size()) {
        char c = data[pos];
        if (c == '(') {
            pos = skip_literal_string(data, pos);
        } else if (c == '%') {
            auto eol = data.find_first_of("\r\n", pos + 1);
            pos = eol == std::string_view::npos ? data.size() : eol + 1;
        } else if (c == '<' && pos + 1 < data.size() && data[pos + 1] == '<') {
            pos += 2;
        } else if (c == '<') {
            auto end = data.find('>', pos + 1);
            if (end == std::string_view::npos)
                end = data.size();
            auto clause = hex_string_problem(data.substr(pos + 1, end - pos - 1));
            if (clause != nullptr) {
                problems.append(py::make_tuple(clause,
                    clause[6] == '1' ? "hex string has an odd number of digits"
                                     : "hex string contains non-hex characters"));
            }
            pos = end + 1;
        } else if (c == 'I' && starts_inline_image_data(data, pos)) {
            // The data begins after the whitespace byte that follows ID
            size_t start = pos + 3;
            if (image == images.size()) {
                problems.append(py::make_tuple(
                    "inline-image", "inline image data cannot be delimited"));
                return problems;
            }
            std::string_view expected(images[image].c_str(), images[image].size());
            image++;
            bool matches = start <= data.size()
                               ? data.substr(start, expected.size()) == expected
                               : expected.empty();
            if (!matches) {
                problems.append(py::make_tuple(
                    "inline-image", "inline image data cannot be delimited"));
                return problems;
            }
            pos = start + expected.size();
        } else {
            pos++;
        }
    }
    if (image < images.size())
        problems.append(
            py::make_tuple("inline-image", "inline image data cannot be delimited"));
    return problems;
}

void init_parsers(py::module_ &m)
{
    py::class_<ContentChecker>(m, "_ContentChecker")
        .def(
            "__init__",
            [](ContentChecker *self,
                py::dict operators,
                py::dict handlers,
                long long min_integer,
                long long max_integer,
                double max_real,
                double min_real,
                size_t max_string,
                size_t max_name,
                std::optional<size_t> max_array,
                std::optional<size_t> max_dict,
                int max_nesting) {
                new (self) ContentChecker(operators,
                    handlers,
                    OperandLimits{min_integer,
                        max_integer,
                        max_real,
                        min_real,
                        max_string,
                        max_name,
                        max_array,
                        max_dict,
                        max_nesting});
            },
            py::arg("operators"),
            py::arg("handlers"),
            py::kw_only(),
            py::arg("min_integer"),
            py::arg("max_integer"),
            py::arg("max_real"),
            py::arg("min_real"),
            py::arg("max_string"),
            py::arg("max_name"),
            py::arg("max_array").none(),
            py::arg("max_dict").none(),
            py::arg("max_nesting"))
        .def("check", &ContentChecker::check, py::arg("stream"));
    m.def("_scan_raw_content",
        &scan_raw_content,
        py::arg("data"),
        py::arg("inline_images"));

    py::class_<ContentStreamInstruction>(
        m, "ContentStreamInstruction", py::type_slots(pikepdf_gc_slots))
        .def(py::init<const ContentStreamInstruction &>())
        .def("__init__",
            [](ContentStreamInstruction *self,
                py::iterable operands,
                QPDFObjectHandle operator_) {
                ObjectList newlist;
                for (const auto &item : operands) {
                    newlist.emplace_back(objecthandle_encode(item));
                }
                new (self) ContentStreamInstruction(newlist, operator_);
            })
        .def_prop_ro(
            "operator", [](ContentStreamInstruction &csi) { return csi.operator_; })
        .def_prop_ro(
            "operands", [](ContentStreamInstruction &csi) { return csi.operands; })
        .def("__getitem__",
            [](ContentStreamInstruction &csi, int index) {
                if (index == 0 || index == -2)
                    return py::cast(csi.operands);
                else if (index == 1 || index == -1)
                    return py::cast(csi.operator_);
                throw py::index_error(
                    (std::string("Invalid index ") + std::to_string(index)).c_str());
            })
        .def("__len__", [](ContentStreamInstruction &csi) { return 2; })
        .def("__repr__", [](ContentStreamInstruction &csi) {
            return "pikepdf.ContentStreamInstruction(" +
                   py::cast<std::string>(py::repr(py::cast(csi.operands))) + ", " +
                   objecthandle_repr(csi.operator_) + ")";
        });

    py::class_<ContentStreamInlineImage>(
        m, "ContentStreamInlineImage", py::type_slots(pikepdf_gc_slots))
        .def(py::init<const ContentStreamInlineImage &>())
        .def("__init__",
            [](ContentStreamInlineImage *self, py::object iimage) {
                auto data = iimage.attr("_data");
                auto image_object = iimage.attr("_image_object");

                new (self) ContentStreamInlineImage(py::cast<ObjectList>(image_object),
                    py::cast<QPDFObjectHandle>(data));
            })
        .def_prop_ro("operator",
            [](ContentStreamInlineImage &csii) {
                return QPDFObjectHandle::newOperator("INLINE IMAGE");
            })
        .def_prop_ro("operands",
            [](ContentStreamInlineImage &csii) { return csii.get_operands(); })
        .def("__getitem__",
            [](ContentStreamInlineImage &csii, int index) -> py::object {
                if (index == 0 || index == -2)
                    return csii.get_operands();
                else if (index == 1 || index == -1)
                    return py::cast(csii.get_operator());
                throw py::index_error(
                    (std::string("Invalid index ") + std::to_string(index)).c_str());
            })
        .def("__len__", [](ContentStreamInlineImage &csii) { return 2; })
        .def_prop_ro("iimage",
            [](ContentStreamInlineImage &csii) { return csii.get_inline_image(); })
        .def("__repr__", [](ContentStreamInlineImage &csii) {
            return "<pikepdf.ContentStreamInlineImage([" +
                   py::cast<std::string>(py::repr(csii.get_inline_image())) +
                   "], pikepdf.Operator('INLINE IMAGE'))>";
        });
}