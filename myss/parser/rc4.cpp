#include "rc4.h"



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
		unsigned char s[1] = { 0 };
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
	//Py_INCREF(d);
	return d;
}

