#ifndef MYPYDEV_H
#define MYPYDEV_H

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

#define PyBytesObject_SIZE (offsetof(PyBytesObject, ob_sval) + 1)
#define GET_BYTE(b, i) ( (unsigned char)(*(b->ob_sval + i)) )	//从PyBytesObject中取出byte

PyObject *
PyBytes_FromSize(Py_ssize_t size, int use_calloc);

#endif