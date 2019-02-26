#include "cares.h"

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
