# -*- coding: utf-8 -*-
    
    # "pyleptonica" is a Python wrapper to Leptonica Library
    # Copyright (C) 2010 João Sebastião de Oliveira Bueno <jsbueno@python.org.br>
    
    #This program is free software: you can redistribute it and/or modify
    #it under the terms of the Lesser GNU General Public License as published by
    #the Free Software Foundation, either version 3 of the License, or
    #(at your option) any later version.

    #This program is distributed in the hope that it will be useful,
    #but WITHOUT ANY WARRANTY; without even the implied warranty of
    #MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    #GNU General Public License for more details.

    #You should have received a copy of the Lesser GNU General Public License
    #along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
This file parses the C language functions and
generates a file that anotates calling parameteers and return types for all
those functions
"""
import re
import sys
from leptonica_header_parser import lepton_types
from config import leptonica_home


lepton_source_dir = leptonica_home + "/src/"
target_file = "leptonica_functions.py"

class FunctionNotExported(Exception):
    pass


def get_file_contents(file_name):
      infile = open(file_name)
      # This is different than what we ar doing for the header files
      text = infile.read()
      infile.close()
      return text
      
# Sample of leptonica C file to understand the parsing functions
"""

/*!
 *  pixAffineSampled()
 *
 *      Input:  pixs (all depths)
 *              vc  (vector of 6 coefficients for affine transformation)
 *              incolor (L_BRING_IN_WHITE, L_BRING_IN_BLACK)
 *      Return: pixd, or null on error
 *
 *  Notes:
 *      (1) Brings in either black or white pixels from the boundary.
 *      (2) Retains colormap, which you can do for a sampled transform..
 *      (3) For 8 or 32 bpp, much better quality is obtained by the
 *          somewhat slower pixAffine().  See that function
 *          for relative timings between sampled and interpolated.
 */
PIX *
pixAffineSampled(PIX        *pixs,
                 l_float32  *vc,
                 l_int32     incolor)
{
l_int32     i, j, w, h, d, x, y, wpls, wpld, color, cmapindex;

"""

def strip_comment(raw_comment):
    comment = ""
    for line in raw_comment.split("\n")[1:]:
        comment += line[2:] + "\n"
    return comment

def parse_file_comment(text):
    # Expression to capture file wide comment :
    expr = re.compile(r"^(\/\*\s*$.*?)^\s\*\/", 
        re.MULTILINE | re.DOTALL)
    comment = expr.findall(text)
    if not comment:
        return ""
    return strip_comment(comment[0])

def parse_prototype(prototype_text):
    prototype = prototype_text.split("\n")
    counter = 0
    last_scaped = False
    # in some files there may be some preprocessor
    # directives between the comment and the function start
    while True:
        line = prototype[counter].strip()
        if (line and (last_scaped or line[0] == "#") and
            line[-1] == "\\"):
            counter += 1
            last_scaped = True
            continue
        if line and line[0] != "#" and not last_scaped:
            break
        counter += 1
        last_scaped = False
    prototype = prototype[counter:]
    prototype_text = " ".join(prototype)
    return_type = prototype[0].strip()

    function_name = prototype[1].split("(")[0].strip()
    if return_type.startswith("static"):
        #print "Static function - not exported: ", function_name
        raise FunctionNotExported
    if function_name in NOT_EXPORTED:
        raise FunctionNotExported
    parameters = []
    parameter_tokens = prototype_text.split("(",
        1)[-1].rsplit(")",1)[0].split(",")
    #print parameter_tokens
    for token in parameter_tokens:
        token = token.strip()
        if not token:
            continue
        if token.startswith("/*"):
            token = token.split("*/",1)[1].strip()
        if "(" in token:
            sys.stderr.write("Unhandled parameter declaration" +
                "- not exporting: %s\n" % function_name)
            raise FunctionNotExported
        if token.strip() == "void":
            break
        try:
            data_type, name = token.rsplit(None,1)
        except Exception as error:
            sys.stderr.write("Unexpected preample/function declaration."
                + " Parsing error:\n\n%s\n" % prototype_text)
            raise
        parameters.append((data_type.strip(), name.strip()))
    return return_type, function_name, parameters 
    
    


def parse_functions(text):
    """We take advantage of the fact that all public 
    C functions in leptonica are  prefixed with /*! style
    comments - these functions are then parsed
    for their documentation, return types and parameter lists
    """
    functions = {}
    # chop everything between a /*! starting line and  a { starting line 
    doc_and_proto_expr = re.compile(r"^(\/\*\!.*?)^{",
        re.MULTILINE | re.DOTALL)
    doc_and_proto = doc_and_proto_expr.findall(text)
    for function in doc_and_proto:
        raw_comment, prototype = function.split("*/", 1)
        comment = strip_comment(raw_comment)
        try:
            if "..." in prototype:
                continue
            return_type, name, arg_list = parse_prototype(prototype)
            functions[name] = (arg_list, return_type, comment)
        except FunctionNotExported:
            continue
    return functions

def parse_file(file_name):
    text = get_file_contents(file_name)
    comment = parse_file_comment(text)
    functions = parse_functions(text)
    return comment, functions

def format_return_type(return_type):
    return_type = return_type.strip()
    indirections = 0
    while return_type.endswith("*"):
        indirections += 1
        return_type = return_type[:-1].strip()
    if return_type.startswith("static"):
        raise FunctionNotExported
    if return_type.startswith("const"):
        return_type = return_type.split(None,1)[-1].strip()
    if return_type == "char" and indirections == 1:
        # Function automatically dealocates string returned by library
        # and creates a python string
        return_type = ("""lambda address: """ + 
            """(ctypes.string_at(address), free(address))[0]""")
    elif return_type == "void" and indirections == 0:
        return_type = "None"
    elif return_type in lepton_types:
        return_type = lepton_types[return_type]
        # MAYBE change these for c_void_p ? 
        for i in xrange(indirections):
            return_type = "ctypes.POINTER(%s)" % return_type
    else: #Return type should be a pointer to one 
          #of the library defined structures
        if indirections == 1:
            return_type = ("lambda address: %s(from_address=address)" % return_type)
        # More than one indirection not promoted to the magic hybrid type:
        elif indirections > 1:
            return_type = "ctypes.c_void_p"
            #for i in xrange(indirections):
                #return_type = "ctypes.POINTER(%s%s)" % ("structs._" if i == 0 else "", return_type)
    return return_type

def format_args(arg_list):
    final_args = []
    for arg_type, arg_name in arg_list:
        indirections = arg_name.count("*")
        if (arg_type.startswith("const") or
            arg_type.startswith("static")):
            arg_type = arg_type.split(None,1)[-1].strip()
        if arg_type in lepton_types:
            arg_type = lepton_types[arg_type]
        if indirections:
            arg_type = "ctypes.c_void_p"
        #for i in xrange(indirections):
            #arg_type = "ctypes.POINTER(%s)" % arg_type
        final_args.append(arg_type)
    #TODO: the referenciation code for each argument
    # must be generated here as well
    # That means: code to translate from python objects
    # to proper ctype parameters
    return final_args
    
# indented to fit inside the generated classes


function_template = '''
    try:
        leptonica.%(name)s.argtypes = [%(argtypes)s]
        leptonica.%(name)s.restype = %(restype)s
    except AttributeError:
        os.stderr.write("Warning - function %(name)s not exported " +
            "by libleptonica\\n\\tCalls to it won't work\\n")
    
    @staticmethod
    def %(name)s(*args):
        """
        %(docstring)s
        """
        args = _convert_params(*args)
        %(referenciation_code)s
        return leptonica.%(name)s(*args)
    
'''

#referenciation_template = '''
       #args = _convert_params(*args)

#'''

def render_functions(functions_dict):
    functions = []
    for name, (arg_list, return_type, function_doc) in \
        functions_dict.items():
        try:
            return_type = format_return_type(return_type)
        except FunctionNotExported:
            os.stderr.write("Function %s not exported. verify.\n" %
                name)
            continue
        function_doc = "       \n".join("%s" % str(args)
            for args in arg_list) + "       \n" + function_doc
        # TODO: transform argument types into proper python names
        final_args = format_args(arg_list)
        argtypes = ", ".join(final_args)
        # TODO: generate the referenciation code
        
        functions.append (function_template %{
            "name": name,
            "argtypes": argtypes,
            "restype": return_type,
            "docstring": function_doc,
            "referenciation_code": "" }
        )
    return "    \n".join(functions)
        

class_template = '''
class %(file_name)s(object):
    """%(docstring)s"""
    %(functions)s

'''

def render_modules(modules):
    classes = {}
    for module in modules:
        module_doc = modules[module][0]
        functions_dict = modules[module][1]
        classes[module] = class_template % {"file_name": module,
                            "docstring": module_doc, 
                            "functions":
                                render_functions(functions_dict)
                            }
    return classes

file_template = """
#coding: utf-8

import ctypes
from leptonica_structures import *
import leptonica_structures as structs

try:
    leptonica = ctypes.cdll.LoadLibrary("liblept.so")
    libc = ctypes.cdll.LoadLibrary("libc.so.6")
except OSError: 
    # Known issue: liblept.so fails to load in ctypes with
    # Ubuntu 10.10 package - probably due to a missing dependence
    #Windows: untested ! 
    import ctypes.util
    leptonica = ctypes.cdll.LoadLibrary("liblept.dll")
    libc = ctypes.cdll.LoadLibrary(ctypes.util.find_msvcrt())

free = libc.free

def _convert_params(*args):
    new_args = []
    for arg in args:
        if isinstance(arg, structs.LeptonObject):
            arg = arg._address_
        new_args.append(arg)
    return tuple(new_args)


%(classes)s

# In C, you don't have to know in which "module" a function lives
# you should not need in Python - All Leptonica functions are agregated here:
functions = type("all_functions", (object,), dict (
        (function_name, function)
        for cls in globals().values() if isinstance(cls, type)
        for function_name, function in cls.__dict__.items()
            if isinstance(function, staticmethod)
    ))

__all__ = %(class_names)s + ["leptonica", "functions"]
"""

def render_file(classes):
    with open(target_file, "wt") as outfile:
        outfile.write(file_template % {"classes":
            "\n".join(classes.values()), 
            "class_names": list(classes.keys())})

def main(file_names):
    modules = {}
    for file_name in file_names:
        module_name = file_name.rsplit(".",1)[0]
        modules[module_name] = parse_file(lepton_source_dir + file_name)
    classes = render_modules(modules)
    render_file(classes)

files = ['adaptmap.c', 'colorcontent.c', 
'numafunc1.c', 'psio1stub.c', 'sel1.c', 'affine.c', 'colormap.c',
'fpix1.c', 'numafunc2.c', 'psio2.c', 'sel2.c', 'affinecompose.c', 
'colormorph.c', 'fpix2.c', 'pageseg.c', 'psio2stub.c', 'selgen.c',
 'colorquant1.c', 'freetype.c', 'paintcmap.c',
'ptabasic.c', 'shear.c', 'arrayaccess.c', 'colorquant2.c', 'gifio.c',
'parseprotos.c', 'ptafunc1.c', 'skew.c', 'arrayaccess.h.vc',
'colorseg.c', 'gifiostub.c', 'partition.c', 'ptra.c',
'spixio.c','bardecode.c', 'compare.c', 'gplot.c', 'pix1.c', 'queue.c',
'stack.c', 'baseline.c', 'conncomp.c', 'graphics.c', 'pix2.c', 'rank.c',
'sudoku.c', 'bbuffer.c', 'convertfiles.c', 'graymorph.c', 'pix3.c',
'readbarcode.c', 'textops.c', 'bilinear.c', 'convolve.c',
'pix4.c', 'readfile.c', 'tiffio.c', 'binarize.c',
'grayquant.c', 'pix5.c', 'regutils.c', 'tiffiostub.c',
'binexpand.c', 'correlscore.c', 'pixabasic.c',
'rop.c', 'utils.c', 'heap.c', 'pixacc.c',
 'viewfiles.c', 'binreduce.c', 'dwacomb.2.c', 'jbclass.c',
'pixafunc1.c', 'warper.c', 
'dwacomblow.2.c', 'jpegio.c', 'pixafunc2.c', 'rotateam.c',
'watershed.c', 'blend.c', 'edge.c', 'jpegiostub.c', 'pixalloc.c',
'webpio.c', 'bmf.c', 'endiantest.c', 'kernel.c',
'pixarith.c', 'rotate.c', 'webpiostub.c', 'bmpio.c', 'enhance.c',
'leptwin.c', 'pixcomp.c', 'rotateorth.c', 'writefile.c', 'bmpiostub.c',
'fhmtauto.c', 'list.c', 'pixconv.c', 
'xtractprotos.c', 'boxbasic.c', 'fhmtgen.1.c', 'makefile.static',
'pixtiling.c', 'rotateshear.c', 'zlibmem.c', 'boxfunc1.c',
'fhmtgenlow.1.c', 'maze.c', 'pngio.c', 'runlength.c', 'zlibmemstub.c',
'boxfunc2.c', 'finditalic.c', 'morphapp.c', 'pngiostub.c', 'sarray.c',
'boxfunc3.c', 'flipdetect.c', 'morph.c', 'pnmio.c', 'scale.c',
'ccbord.c', 'fliphmtgen.c', 'morphdwa.c', 'pnmiostub.c',
'ccthin.c', 'fmorphauto.c', 'morphseq.c', 'projective.c', 'seedfill.c',
'classapp.c', 'fmorphgen.1.c', 'numabasic.c', 'psio1.c']

# Some "perfectly good" functions simply are not exported 
# as of leptonica 1.6.7
NOT_EXPORTED = set(["pixGetForegroundGrayMap",
    "pixRandomHarmonicWarpLUT", "pixGetWindowsHBITMAP"])

if __name__ == "__main__":
    # FIXME:
    # The files of type ".1.c"  are being skipped for now, mostly
    # due to not respecting the comment format prefixing the functions
    # (they miss the ! marker in th  /*! comments 
    main([filename for filename in files if filename.count(".") == 1])
