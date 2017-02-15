#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFObjGen.hh>
#include <qpdf/QPDFXRefEntry.hh>
#include <qpdf/PointerHolder.hh>
#include <qpdf/Buffer.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFWriter.hh>

#include <sstream>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>


using namespace std::literals::string_literals;

namespace py = pybind11;


//PYBIND11_DECLARE_HOLDER_TYPE(T, PointerHolder<T>);

/*
New type table

Encode Python type to C++ type
Decode C++ type to Python

Definite native:
Null - None
Boolean - bool
Integer - int
Real - Decimal

Uncertain:
String - str or bytes ?

Convertible:
Name - Name('/thing') 
Operator - Operator('Do')
Array - list / iterable
Dictionary - dict
Stream - Stream()


*/


std::string objecthandle_scalar_value(QPDFObjectHandle h)
{
    switch (h.getTypeCode()) {
    case QPDFObject::object_type_e::ot_null:
        return "None";
    case QPDFObject::object_type_e::ot_boolean:
        return (h.getBoolValue() ? "True" : "False");
    case QPDFObject::object_type_e::ot_integer:
        return std::to_string(h.getIntValue());
    case QPDFObject::object_type_e::ot_real:
        return "Decimal('"s + h.getRealValue() + "')"s;
    case QPDFObject::object_type_e::ot_name:
        return "qpdf.Object.Name('"s + h.getName() + "')"s;
    case QPDFObject::object_type_e::ot_string:
        return h.getUTF8Value();
    case QPDFObject::object_type_e::ot_operator:
        return h.getOperatorValue();
    default:
        return "<not a scalar>";
    }
}

std::string objecthandle_pythonic_typename(QPDFObjectHandle h, std::string prefix = "qpdf.Object.")
{
    std::string s;

    s += prefix;
    switch (h.getTypeCode()) {
    case QPDFObject::object_type_e::ot_null:
        s += "Null";
        break;
    case QPDFObject::object_type_e::ot_boolean:
        s += "Boolean";
        break;
    case QPDFObject::object_type_e::ot_integer:
        s += "Integer";
        break;
    case QPDFObject::object_type_e::ot_real:
        s += "Real";
        break;
    case QPDFObject::object_type_e::ot_name:
        s += "Name";
        break;
    case QPDFObject::object_type_e::ot_string:
        s += "String";
        break;
    case QPDFObject::object_type_e::ot_operator:
        s += "Operator";
        break;
    case QPDFObject::object_type_e::ot_inlineimage:
        s += "InlineImage";
        break;
    case QPDFObject::object_type_e::ot_array:
        s += "Array";
        break;
    case QPDFObject::object_type_e::ot_dictionary:
        s += "Dictionary";
        break;
    case QPDFObject::object_type_e::ot_stream:
        s += "Stream";
        break;
    default:
        s += "<Error>";
        break;
    }

    return s;
}


std::string objecthandle_repr_typename_and_value(QPDFObjectHandle h)
{
    return objecthandle_pythonic_typename(h) + \
                "("s + objecthandle_scalar_value(h) + ")"s;
}


std::string objecthandle_repr_inner(QPDFObjectHandle h, int depth, std::set<QPDFObjGen>* visited, bool* pure_expr)
{
    if (!h.isScalar()) {
        if (visited->count(h.getObjGen()) > 0) {
            *pure_expr = false;
            return "<circular reference>";
        }

        if (!(h.getObjGen() == QPDFObjGen(0, 0)))
            visited->insert(h.getObjGen());
    }

    std::ostringstream oss;

    switch (h.getTypeCode()) {
    case QPDFObject::object_type_e::ot_null:
    case QPDFObject::object_type_e::ot_boolean:
    case QPDFObject::object_type_e::ot_integer:
    case QPDFObject::object_type_e::ot_real:
    case QPDFObject::object_type_e::ot_name:
    case QPDFObject::object_type_e::ot_string:
        oss << objecthandle_scalar_value(h);
        break;
    case QPDFObject::object_type_e::ot_operator:
        oss << objecthandle_repr_typename_and_value(h);
        break;
    case QPDFObject::object_type_e::ot_inlineimage:
        oss << objecthandle_pythonic_typename(h);
        oss << "(";
        oss << "data=<...>";
        oss << ")";
        break;
    case QPDFObject::object_type_e::ot_array:
        oss << "[";
        {
            bool first = true;
            oss << " ";
            for (auto item: h.getArrayAsVector()) {
                if (!first) oss << ", ";
                first = false;
                oss << objecthandle_repr_inner(item, depth, visited, pure_expr);
            }
            oss << " ";
        }
        oss << "]";
        break;
    case QPDFObject::object_type_e::ot_dictionary:
        oss << "{"; // This will end the line
        {
            bool first = true;
            oss << "\n";
            for (auto item: h.getDictAsMap()) {
                if (!first) oss << ",\n";
                first = false;
                oss << std::string((depth + 1) * 2, ' '); // Indent each line
                oss << "'" << item.first << "': " << objecthandle_repr_inner(item.second, depth + 1, visited, pure_expr);
            }
            oss << "\n";
        }
        oss << std::string(depth * 2, ' '); // Restore previous indent level
        oss << "}";
        break;
    case QPDFObject::object_type_e::ot_stream:
        *pure_expr = false;
        oss << objecthandle_pythonic_typename(h);
        oss << "(";
        oss << "stream_dict=";
        oss << objecthandle_repr_inner(h.getDict(), depth + 1, visited, pure_expr);
        oss << ", ";
        oss << "data=<...>";
        oss << ")";
        break;
    default:
        oss << "???";
        break;
    }

    return oss.str();
}

std::string objecthandle_repr(QPDFObjectHandle h)
{
    if (h.isScalar()) {
        return objecthandle_repr_typename_and_value(h);
    }

    std::set<QPDFObjGen> visited;
    bool pure_expr = true;
    std::string inner = objecthandle_repr_inner(h, 0, &visited, &pure_expr);
    std::string output;

    if (h.isScalar() || h.isDictionary() || h.isArray()) {
        output = objecthandle_pythonic_typename(h) + "("s + inner + ")"s;
    } else {
        output = inner;
        pure_expr = false;
    }

    if (pure_expr) {
        // The output contains no external or parent objects so this object
        // can be output as a Python expression and rebuild with repr(output)
        return output;
    }
    // Output cannot be fully described in a Python expression
    return "<"s + output + ">"s;
}


QPDFObjectHandle objecthandle_from_scalar(py::handle obj)
{
    try {
        auto as_obj = obj.cast<QPDFObjectHandle>();
        return as_obj;
    } catch (py::cast_error) {}

    try {
        auto as_bool = obj.cast<bool>();
        return QPDFObjectHandle::newBool(as_bool);
    } catch (py::cast_error) {}

    try {
        auto as_int = obj.cast<int>();
        return QPDFObjectHandle::newInteger(as_int);
    } catch (py::cast_error) {}

    try {
        auto as_double = obj.cast<double>();
        return QPDFObjectHandle::newReal(as_double);
    } catch (py::cast_error) {}

    try {
        auto as_str = obj.cast<std::string>();
        return QPDFObjectHandle::newString(as_str);
    } catch (py::cast_error) {}

    if (obj == py::handle()) {
        return QPDFObjectHandle::newNull();
    }

    throw py::cast_error("not scalar");
}


std::vector<QPDFObjectHandle>
array_builder(py::iterable iter);

std::map<std::string, QPDFObjectHandle>
dict_builder(py::dict dict)
{
    std::map<std::string, QPDFObjectHandle> result;

    for (auto item: dict) {
        std::string key = item.first.cast<std::string>();

        try {
            auto value = objecthandle_from_scalar(item.second);
            result[key] = value;
        } catch (py::cast_error) {
            if (PyMapping_Check(item.second.ptr())) {
                auto as_dict = item.second.cast<py::dict>();
                auto subdict = dict_builder(as_dict);
                result[key] = QPDFObjectHandle::newDictionary(subdict);
            } else if (PySequence_Check(item.second.ptr())) {
                auto as_list = item.second.cast<py::iterable>();
                auto sublist = array_builder(as_list);
                result[key] = QPDFObjectHandle::newArray(sublist);
            } else {
                throw py::value_error(
                    "dict_builder: don't know how to parse value associated with "s + key);
            }
        }
    }
    return result;
}

std::vector<QPDFObjectHandle>
array_builder(py::iterable iter)
{
    std::vector<QPDFObjectHandle> result;
    int narg = 0;

    for (auto item: iter) {
        narg++;
        try {
            auto value = objecthandle_from_scalar(item);
            result.push_back(value);
        } catch (py::cast_error) {
            if (PyMapping_Check(item.ptr())) {
                auto as_dict = item.cast<py::dict>();
                auto subdict = dict_builder(as_dict);
                result.push_back(QPDFObjectHandle::newDictionary(subdict));
            } else if (PySequence_Check(item.ptr())) {
                auto as_list = item.cast<py::iterable>();
                auto sublist = array_builder(as_list);
                result.push_back(QPDFObjectHandle::newArray(sublist));
            } else {
                throw py::value_error(
                    "array_builder: don't know how to parse argument "s + std::to_string(narg));
            }
        }
    }
    return result;
}


py::object objecthandle_decode(QPDFObjectHandle& h)
{
    py::object obj = py::none();

    switch (h.getTypeCode()) {
    case QPDFObject::object_type_e::ot_null:
        return py::none();
    case QPDFObject::object_type_e::ot_boolean:
        obj = py::cast(h.getBoolValue());
        break;
    case QPDFObject::object_type_e::ot_integer:
        obj = py::cast(h.getIntValue());
        break;
    case QPDFObject::object_type_e::ot_real:
        {
            auto decimal_constructor = py::module::import("decimal").attr("Decimal");
            std::string value = h.getRealValue();
            obj = decimal_constructor(py::cast(value)); 
        }
        break;
    case QPDFObject::object_type_e::ot_name:
        break;
    case QPDFObject::object_type_e::ot_string:
        obj = py::bytes(h.getStringValue());
        break;
    case QPDFObject::object_type_e::ot_operator:
        break;
    case QPDFObject::object_type_e::ot_inlineimage:
        break;
    case QPDFObject::object_type_e::ot_array:
        break;
    case QPDFObject::object_type_e::ot_dictionary:
        break;
    case QPDFObject::object_type_e::ot_stream:
        break;
    default:
        break;
    }

    if (obj == py::none())
        throw py::type_error("not decodable"); 

    return obj;
}



class PyParserCallbacks : public QPDFObjectHandle::ParserCallbacks {
public:
    using QPDFObjectHandle::ParserCallbacks::ParserCallbacks;

    void handleObject(QPDFObjectHandle h) override {
        PYBIND11_OVERLOAD_PURE_NAME(
            void,
            QPDFObjectHandle::ParserCallbacks,
            "handle_object", /* Python name */
            handleObject, /* C++ name */
            h
        );
    }

    void handleEOF() override {
        PYBIND11_OVERLOAD_PURE_NAME(
            void,
            QPDFObjectHandle::ParserCallbacks,
            "handle_eof", /* Python name */
            handleEOF, /* C++ name; trailing comma needed for macro */
        );
    }
};


void init_object(py::module& m)
{
    //py::class_<QPDFObject> qpdfobject(m, "_QPDFObject");
    py::enum_<QPDFObject::object_type_e>(m, "ObjectType")
        .value("ot_uninitialized", QPDFObject::object_type_e::ot_uninitialized)
        .value("ot_reserved", QPDFObject::object_type_e::ot_reserved)
        .value("ot_null", QPDFObject::object_type_e::ot_null)
        .value("ot_boolean", QPDFObject::object_type_e::ot_boolean)
        .value("ot_integer", QPDFObject::object_type_e::ot_integer)
        .value("ot_real", QPDFObject::object_type_e::ot_real)
        .value("ot_string", QPDFObject::object_type_e::ot_string)
        .value("ot_name", QPDFObject::object_type_e::ot_name)
        .value("ot_array", QPDFObject::object_type_e::ot_array)
        .value("ot_dictionary", QPDFObject::object_type_e::ot_dictionary)
        .value("ot_stream", QPDFObject::object_type_e::ot_stream)
        .value("ot_operator", QPDFObject::object_type_e::ot_operator)
        .value("ot_inlineimage", QPDFObject::object_type_e::ot_inlineimage);

/* Object API

qpdf.Object.Typename()  <-- class-ish name, static method in reality
tries to coerce input to PDF object of typename, or fails

qpdf.Object.new() <--- tries to create a PDF object from its input with when
possible without ambiguity

Boolean <- bool
Integer <- int
Real <- decimal.Decimal, float
String <- str, bytes
    this will need help from PDF doc encoding

Array <- list, tuple
Dictionary <- dict, Mapping

Stream <- present as qpdf.Object.Stream({dictionary}, stream=<...>)

when does Dictionary.__setitem__ coerce its value to a PDF object? on input
or serialization
    probably on input, fail first

that means __setitem__ needs to recursively coerce

should be able to assign python objects and have them mapped to appropriate
objects - or




// qpdf.Object.Boolean(True) <-- class-ish name, static method in reality
// instead of
// qpdf.Object.new(True)  <--- when possible without ambiguity
// strings:
// qpdf.Object.Name("")
// qpdf.Object.new("/Name"?)

// Then repr becomes...
// or should each object be type-decorated?
qpdf.Object.Dictionary({
    "/Type": "/Page",
    "/MediaBox": [],
    "/Contents": <qpdf.Object.Stream>,
})

PointerHolder<T> is a homebrewed shared_ptr within qpdf that is not compatible
with the API of pybind11.  Options include a PointerHolderHolder to translate
or the approach taken so far which is to not let PointerHolders escape into
the wide and instead create private Python copies

*/

    // py::class_<Buffer, PointerHolder<Buffer>>(m, "Buffer")
    //     .def_property_readonly("size", &Buffer::getSize)
    //     .def("readall",
    //         [](Buffer &buf) {
    //             return reinterpret_cast<char *>(buf.getBuffer());
    //         }
    //     );

    py::class_<QPDFObjectHandle> objecthandle(m, "Object");

    objecthandle
        .def_static("Boolean",
            [](bool b) {
                return QPDFObjectHandle::newBool(b);
            }
        )
        .def_static("Integer",
            [](int n) {
                return QPDFObjectHandle::newInteger(n);
            }
        )
        .def_static("Real",
            [](double val, int decimal_places = 0) {
#if 0
                auto scope = py::dict(py::module::import("decimal").attr("__dict__"));
                auto local = py::dict();

                local['obj'] = o;
                auto result = py::eval<py::eval_statements>(R"python(
                    if instanceof(obj, Decimal):
                        out = str(obj)
                    try:
                        out = str(Decimal(obj))
                    except:
                        out = None
                    )python", scope, local);

                if (result != py::none())
                    throw py::value_error("don't know how to make Real from object");

                auto out = local["out"].cast<std::string>();
                return QPDFObjectHandle::newReal(out); //broken
#else
                return QPDFObjectHandle::newReal(val, decimal_places);
#endif
            },
            "create a Real from a float",
            py::arg("val"),
            py::arg("decimal_places") = py::int_(0)
        )
        .def_static("Name",
            [](const std::string& s) {
                if (s.at(0) != '/')
                    throw py::value_error("Name objects must begin with '/'");
                if (s.length() < 2)
                    throw py::value_error("Name must be at least one character long");
                return QPDFObjectHandle::newName(s);
            },
            "Create a Name from a string. Must begin with '/'. All other characters except null are valid."
        )
        .def_static("String",
            [](const std::string& s) {
                return QPDFObjectHandle::newString(s);
            }
        )
        .def_static("Array",
            [](py::iterable iterable) {
                return QPDFObjectHandle::newArray(array_builder(iterable));
            }
        )
        .def_static("Dictionary",
            [](py::dict dict) {
                return QPDFObjectHandle::newDictionary(dict_builder(dict));
            }
        )
        .def_static("Stream",
            [](QPDF* owner, py::bytes data) {
                std::string s = data;
                return QPDFObjectHandle::newStream(owner, data); // This makes a copy of the data
            },
            py::keep_alive<1, 2>() // this-> (arg1) keeps a copy of QPDF* (arg2)
        ) 
        .def_static("Null", &QPDFObjectHandle::newNull)
        .def_static("new",
            [](bool b) {
                return QPDFObjectHandle::newBool(b);
            }
        )
        .def_static("new",
            [](int n) {
                return QPDFObjectHandle::newInteger(n);
            }
        )
        .def_static("new",
            [](float f) {
                return QPDFObjectHandle::newReal(f, 0); // default to six decimals
            }
        )
        .def_static("new",
            [](std::string s) {
                return QPDFObjectHandle::newString(s); // TO DO: warn about /Name
            }
        )
        .def_static("new",
            [](py::none none) {
                return QPDFObjectHandle::newNull();
            }
        )
        .def_property_readonly("type_code", &QPDFObjectHandle::getTypeCode)
        .def_property_readonly("type_name", &QPDFObjectHandle::getTypeName)
        .def_property_readonly("owner", &QPDFObjectHandle::getOwningQPDF,
            "Return the QPDF object that owns an indirect object.  Returns None for a direct object."
        )
        .def("__repr__", &objecthandle_repr)
        .def("__eq__",
            [](QPDFObjectHandle &self, QPDFObjectHandle &other) {
                if (!self.isInitialized() || !other.isInitialized())
                    throw py::value_error("equality undefined for uninitialized object handles");
                if (self.getTypeCode() != other.getTypeCode())
                    return false;

                switch (self.getTypeCode()) {
                    case QPDFObject::object_type_e::ot_null:
                        return true; // Both must be null
                    case QPDFObject::object_type_e::ot_boolean:
                        return self.getBoolValue() == other.getBoolValue();
                    case QPDFObject::object_type_e::ot_integer:
                        return self.getIntValue() == other.getIntValue();
                    case QPDFObject::object_type_e::ot_real:
                        throw py::value_error("real comparison not implemented");
                    case QPDFObject::object_type_e::ot_name:
                        return self.getName() == other.getName();
                    case QPDFObject::object_type_e::ot_string:
                        return self.getStringValue() == other.getStringValue();
                    default:
                        throw py::value_error("comparison undefined");
                }
            }
        )
        .def("__len__",
            [](QPDFObjectHandle &h) {
                if (h.isDictionary())
                    return (Py_ssize_t)h.getDictAsMap().size(); // getKeys constructs a new object, so this is better
                else if (h.isArray())
                    return (Py_ssize_t)h.getArrayNItems();
                throw py::value_error("length not defined for object");
            }
        )
        .def("__getitem__",
            [](QPDFObjectHandle &h, std::string const& key) {
                if (!h.isDictionary())
                    throw py::value_error("object is not a dictionary");
                if (!h.hasKey(key))
                    throw py::key_error(key);
                return h.getKey(key);
            }
        )
        .def("__setitem__",
            [](QPDFObjectHandle &h, std::string const& key, QPDFObjectHandle &value) {
                if (!h.isDictionary())
                    throw py::value_error("object is not a dictionary");

                if (value.getOwningQPDF() && value.getOwningQPDF() != h.getOwningQPDF())
                    throw py::value_error("cannot assign indirect object from a foreign PDF - use copyForeignObject");

                if (value.isScalar()) {
                    h.replaceKey(key, value);
                    return;
                }

                try {
                    auto copy = value.shallowCopy();
                    copy.makeDirect();
                } catch (std::exception &e) {
                    throw py::value_error("this object is too complex for me to copy right now");
                }
                h.replaceKey(key, value);
            },
            "assign dictionary key to new object",
            py::keep_alive<1, 3>()
        )
        .def("__delitem__",
            [](QPDFObjectHandle &h, std::string const& key) {
                if (!h.isDictionary())
                    throw py::value_error("object is not a dictionary");

                if (!h.hasKey(key))
                    throw py::key_error(key);

                h.removeKey(key);
            },
            "delete a dictionary key"
        )
        .def("get",
            [](QPDFObjectHandle &h, std::string const& key, py::object default_) {
                if (!h.isDictionary())
                    throw py::value_error("object is not a dictionary");
                if (!h.hasKey(key))
                    return default_;
                return py::cast(h.getKey(key));
            },
            "for dictionary objects, behave as dict.get(key, default=None)",
            py::arg("key"),
            py::arg("default_") = py::none()
        )
        .def("keys", &QPDFObjectHandle::getKeys)
        .def("__contains__",
            [](QPDFObjectHandle &h, std::string const& key) {
                if (h.isDictionary()) {
                    return h.hasKey(key);
                }
                throw py::value_error("__contains__ not defined for object type");
            }
        )
        .def("as_list", &QPDFObjectHandle::getArrayAsVector)
        .def("as_dict", &QPDFObjectHandle::getDictAsMap)
        .def("as_int", &QPDFObjectHandle::getIntValue)
        .def("as_bool", &QPDFObjectHandle::getBoolValue)
        .def("decode", objecthandle_decode, "convert to nearest Python object")
        .def("__getitem__",
            [](QPDFObjectHandle &h, int index) {
                if (!h.isArray())
                    throw py::value_error("object is not an array");
                if (!(0 <= index && index < h.getArrayNItems()))
                    throw py::index_error("index out of bounds");
                return h.getArrayItem(index);
            }
        )
        .def_property_readonly("stream_dict", &QPDFObjectHandle::getDict)  // Not actually readonly
        .def("read_stream_data",
            [](QPDFObjectHandle &h) {
                PointerHolder<Buffer> phbuf = h.getStreamData();
                const Buffer* buf = phbuf.getPointer();
                return py::bytes((const char *)buf->getBuffer(), buf->getSize());
            }
        )
        .def_property_readonly("_objgen",
            [](QPDFObjectHandle &h) {
                auto objgen = h.getObjGen();
                return std::pair<int, int>(objgen.getObj(), objgen.getGen());
            }
        )
        .def_static("parse",
            (QPDFObjectHandle (*)(const std::string&, const std::string&)) (&QPDFObjectHandle::parse)
        )
        .def_static("parse_stream", &QPDFObjectHandle::parseContentStream)
        .def("unparse", &QPDFObjectHandle::unparse)
        .def("unparse_resolved", &QPDFObjectHandle::unparseResolved);

    py::class_<QPDFObjectHandle::ParserCallbacks, PyParserCallbacks> parsercallbacks(m, "StreamParser");
    parsercallbacks
        .def(py::init<>())
        .def("handle_object", &QPDFObjectHandle::ParserCallbacks::handleObject)
        .def("handle_eof", &QPDFObjectHandle::ParserCallbacks::handleEOF);

} // init_object
