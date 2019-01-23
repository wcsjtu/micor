#include "cares.h"

extern PyTypeObject *DNSParserTypePtr;

void RC4(unsigned char* key, int keylen, unsigned char* data, int datalen){
	INIT_SBOX(s);
	MESS_SBOX(s, key, keylen)
		int i = 0, j = 0;
	for (int c = 0; c < datalen; c++){
		i = (i + 1) % SBOX_LEN;
		j = (j + s[i]) % SBOX_LEN;
		SWAP_BYTE(s[i], s[j])
			data[c] = data[c] ^ s[(s[i] + s[j]) % SBOX_LEN];
	}
}

PyObject*
PyRC4(PyObject* mod, PyObject* op){
	PyObject* tmp = NULL;
	PyObject* k = NULL;
	if (!PyArg_ParseTuple(op, "SS", &tmp, &k)){
		return NULL;
	}
	unsigned char* key = (unsigned char*)((PyBytesObject*)k)->ob_sval;
	size_t klen = ((PyBytesObject*)k)->ob_base.ob_size;
	size_t dlen = ((PyBytesObject*)tmp)->ob_base.ob_size;

	if (klen <= 0){
		PyErr_SetString(PyExc_RuntimeError, "key is an empty bytes object");
		return NULL;
	}
	if (dlen == 0){
		return tmp;
	}

	if (dlen == 1){
		unsigned char s[1] = {0};
		s[0] = ((PyBytesObject*)tmp)->ob_sval[0];
		RC4(key, klen, s, dlen);
		PyObject* d = PyBytes_FromStringAndSize((const char*)s, 1);
		return d;
	}

	PyObject* d = PyBytes_FromSize(dlen, 0);
	if (d == NULL){
		return PyErr_NoMemory();
	}
	unsigned char* dc = (unsigned char*)(((PyBytesObject*)d)->ob_sval);
	memcpy(dc, ((PyBytesObject*)tmp)->ob_sval, dlen);
	
	RC4(key, klen, dc, dlen);
	Py_INCREF(d);
	return d;
}


void RR_dealloc(RR* self){
	Py_XDECREF(self->domain_name);
	Py_XDECREF(self->value);
	Py_TYPE(self)->tp_free((PyObject*)self);
}

PyObject*
RR_new(PyTypeObject *type, PyObject *args, PyObject *kwds){
	RR* self;
	self = (RR*)type->tp_alloc(type, 0);
	if (self != NULL){
		self->domain_name = (PyBytesObject*)PyBytes_FromString("");
		if (self->domain_name == NULL){
			Py_DECREF(self);
			return NULL;
		}

		self->value = (PyBytesObject*)PyBytes_FromString("");
		if (self->value == NULL){
			Py_DECREF(self);
			return NULL;
		}
		self->qtype = 0;
		self->qcls = 0;
		self->ttl = 0;
	}
	return (PyObject*)self;
}

int
RR_init(RR*self, PyObject *args, PyObject *kwds){
	PyObject* dn = NULL, *val = NULL, *tmp;
	if (!PyArg_ParseTuple(args, "SSHHH", &dn, &val, &self->qtype, &self->qcls, &self->ttl)){
		return -1;
	}

	if (dn){
		tmp = (PyObject*)self->domain_name;
		Py_INCREF(dn);
		self->domain_name = (PyBytesObject*)dn;
		Py_XDECREF(tmp);
	}

	if (val){
		tmp = (PyObject*)self->value;
		Py_INCREF(val);
		self->value = (PyBytesObject*)val;
		Py_XDECREF(tmp);
	}
	return 0;
}

static PyMemberDef RR_members[] = {
	{ "domain_name", T_OBJECT_EX, offsetof(RR, domain_name), 0, "domain name parsed from dns response" },
	{ "value", T_OBJECT_EX, offsetof(RR, value), 0, "value parsed from dns response, may ip or cname" },
	{ "qtype", T_USHORT, offsetof(RR, qtype), READONLY, "query type of resource record. `READONLY`" },
	{ "qcls", T_USHORT, offsetof(RR, qcls), READONLY, "query class of resource record. `READONLY`" },
	{ "ttl", T_UINT, offsetof(RR, ttl), READONLY, "ttl of resource record. `READONLY`" },
	{NULL}
};

PyDoc_STRVAR(RR_doc,
	"RR(domain_name: bytes, value: bytes, qtype: int, qcls: int, ttl: int) -> RR object\n\
	resource record of DNS, see https://www.ietf.org/rfc/rfc1035.txt for detail");

PyTypeObject RRType = {
	PyVarObject_HEAD_INIT(NULL, 0)	//PyObject_VAR_HEAD
	"cares.RR",						//tp_name,
	sizeof(RR),						//tp_basicsize
	0,								//tp_itemsize
	(destructor)RR_dealloc,			//tp_dealloc
	0,								//tp_print
	0,								//tp_getattr
	0,								//tp_setattr
	0,								//tp_as_async
	0,								//tp_repr
	0,								//tp_as_number
	0,								//tp_as_sequence
	0,								//tp_as_mapping
	0,								//tp_hash
	0,								//tp_call
	0,								//tp_str,
	0,								//tp_getattro
	0,								//tp_setattro
	0,								//tp_as_buffer
	Py_TPFLAGS_DEFAULT,				//tp_flags
	RR_doc,		//tp_doc
	0,								//tp_traverse
	0,								//tp_clear
	0,								//tp_richcompare
	0,								//tp_weaklistoffset
	0,								//tp_iter
	0,								//tp_iternext
	0,								//tp_methods
	RR_members,						//tp_members
	0,								//tp_getset
	0,								//tp_base
	0,								//tp_dict
	0,								//tp_descr_get
	0,								//tp_descr_set
	0,								//tp_dictoffset
	(initproc)RR_init,				//tp_init
	0,								//tp_alloc
	RR_new							//tp_new
};

PyDoc_STRVAR(PyRC4_doc, 
	"rc4(text: bytes, key: bytes) -> bytes\n\
	\n\
	RC4 en/decryptor");

static PyMethodDef module_methods[] = {
	{ "rc4", (PyCFunction)PyRC4, METH_VARARGS, PyRC4_doc },
	{ NULL, NULL, 0, NULL }
};

static struct PyModuleDef cares = {
	PyModuleDef_HEAD_INIT,
	"cares",
	"Copyright 2019-2019 wcsjtu\n\nRR\n\nversion:1.0",
	-1,
	module_methods
};

#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
#define PyMODINIT_FUNC void
#endif

PyMODINIT_FUNC
PyInit_cares(void){
	PyObject* m = PyModule_Create(&cares);
	if (!m){
		return NULL;
	}
	if (PyType_Ready(&RRType) < 0 ||
		PyType_Ready(DNSParserTypePtr) < 0){
		return NULL;
	}

	Py_INCREF(&RRType);
	PyModule_AddObject(m, "RR", (PyObject*)&RRType);
	PyModule_AddObject(m, "DNSParser", (PyObject*)DNSParserTypePtr);
	return m;
}