#ifndef _PYEXT_H
#define _PYEXT_H
#ifdef _DEBUG
#define DEBUG_DEFINED 1
#undef _DEBUG
#endif

#include "Python.h"

#ifdef DEBUG_DEFINED
#define _DEBUG 1
#endif // DEBUG_DEFINED
#endif
#include "structmember.h"

typedef struct {
	PyObject_HEAD
	PyBytesObject* domain_name;
	PyBytesObject* value;
	unsigned short qtype;
	unsigned short qcls;
	unsigned int ttl;
}RR;

PyObject* RR_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
int RR_init(RR*self, PyObject *args, PyObject *kwds);
void RR_dealloc(RR* self);

typedef struct {
	PyObject_HEAD
	PyBytesObject* data;
	unsigned int offset;
} DNSParser;

