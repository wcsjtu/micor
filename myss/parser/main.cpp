#include "main.h"


static PyMethodDef module_methods[] = {
	{ "rc4", (PyCFunction)PyRC4, METH_VARARGS, PyRC4_doc },
	{ "parse_socks5_header", (PyCFunction)parse_socks5_header, METH_O, parse_socks5_header_doc },
	{ "build_ping_pkg", (PyCFunction)PyBuild_ping_pkg, METH_VARARGS, bpp_doc },
	{ "parse_ping_pkg", (PyCFunction)PyParse_ping_pkg, METH_O, ppp_doc},
	{ NULL, NULL, 0, NULL }
};

static struct PyModuleDef cares = {
	PyModuleDef_HEAD_INIT,
	"cares",
	"Copyright 2019-2019 wcsjtu\n\nspeed up python code\n\nversion:1.0",
	-1,
	module_methods
};

PyMODINIT_FUNC
PyInit_cares(void){
	PyObject* m = PyModule_Create(&cares);
	if (!m){
		return NULL;
	}
	if (PyType_Ready(&RRType) < 0 ||
		PyType_Ready(&DNSParserType) < 0 ||
		PyType_Ready(&SocksHeaderType) < 0 ||
		PyType_Ready(&PyICMPFrameType) < 0){
		return NULL;
	}

	Py_INCREF(&RRType);
	Py_INCREF(&SocksHeaderType);
	PyModule_AddObject(m, "RR", (PyObject*)&RRType);
	PyModule_AddObject(m, "DNSParser", (PyObject*)&DNSParserType);
	PyModule_AddObject(m, "SocksHeader", (PyObject*)&SocksHeaderType);
	PyModule_AddObject(m, "ICMPFrame", (PyObject*)&PyICMPFrameType);
	return m;
}