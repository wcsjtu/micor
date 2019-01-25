#ifndef CARES_H
#define CARES_H

#include "mypydev.h"

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

#endif