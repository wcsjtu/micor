#include "mypydev.h"

static PyBytesObject *nullstring;

PyObject *
PyBytes_FromSize(Py_ssize_t size, int use_calloc)
{
	PyBytesObject *op;
	assert(size >= 0);

	if (size == 0 && (op = nullstring) != NULL) {
#ifdef COUNT_ALLOCS
		null_strings++;
#endif
		Py_INCREF(op);
		return (PyObject *)op;
	}

	if ((size_t)size > (size_t)PY_SSIZE_T_MAX - PyBytesObject_SIZE) {
		PyErr_SetString(PyExc_OverflowError,
			"byte string is too large");
		return NULL;
	}

	/* Inline PyObject_NewVar */
	if (use_calloc)
		op = (PyBytesObject *)PyObject_Calloc(1, PyBytesObject_SIZE + size);
	else
		op = (PyBytesObject *)PyObject_Malloc(PyBytesObject_SIZE + size);
	if (op == NULL)
		return PyErr_NoMemory();
	(void)PyObject_INIT_VAR(op, &PyBytes_Type, size);
	op->ob_shash = -1;
	if (!use_calloc)
		op->ob_sval[size] = '\0';
	/* empty byte string singleton */
	if (size == 0) {
		nullstring = op;
		Py_INCREF(op);
	}
	return (PyObject *)op;
}
