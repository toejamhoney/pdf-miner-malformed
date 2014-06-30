#!/usr/bin/env python
#
# dumppdf.py - dump pdf contents in XML format.
#
#  usage: dumppdf.py [options] [files ...]
#  options:
#    -i objid : object id
#
import sys, os.path, re
from pdfminer.psparser import PSKeyword, PSLiteral, LIT
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument, PDFNoOutlines
from pdfminer.pdftypes import PDFObjectNotFound, PDFValueError
from pdfminer.pdftypes import PDFStream, PDFObjRef, resolve1, stream_value
from pdfminer.pdfpage import PDFPage
from pdfminer.utils import isnumber
import traceback


ESC_PAT = re.compile(r'[\000-\037&<>()"\042\047\134\177-\377]')
def e(s):
    return ESC_PAT.sub(lambda m:'&#%d;' % ord(m.group(0)), s)


# dumpxml
def dumpxml(obj, codec=None):
    #print "dumpxml"
    res = ""
    if obj is None:
        res += '<null />'
        return res

    if isinstance(obj, dict):
        #print "dict"
        res += '<dict size="%' + str(len(obj)) + '">\n'
        for (k,v) in obj.iteritems():
            #print "dict loop"
            res += '<key>' + k + '</key>\n'
            res += '<value>'
            res += dumpxml( v)
            #print "after v dump"
            res += '</value>\n'
        res += '</dict>'
        #print "return dict"
        return res

    if isinstance(obj, list):
        #print "list"
        res += '<list size="' + str(len(obj)) + '">\n'
        for v in obj:
            #print "before list dump"
            res += dumpxml(v)
            #print "after list dump"
            res += '\n'
        res += '</list>'
        return res

    if isinstance(obj, str):
        #print "string"
        res += '<string size="' + str(len(obj)) + '">' + e(obj) + '</string>'
        return res

    if isinstance(obj, PDFStream):
        #print "PDFStream"
        if codec == 'raw':
            res += obj.get_rawdata()
        elif codec == 'binary':
            res += obj.get_data()
        else:
            res += '<stream>\n<props>\n'
            #print "before dump attrs"
            res += dumpxml(obj.attrs)
            #print "after dump attrs"
            res += '\n</props>\n'
            if codec == 'text':
                data = obj.get_data()
                res += '<data size="' + str(len(data)) + '">' + e(data) + '</data>\n'
            res += '</stream>'
        return res

    if isinstance(obj, PDFObjRef):
        #print "PDFObjRef"
        res += '<ref id="' + str(obj.objid) + '" />'
        return res

    if isinstance(obj, PSKeyword):
        #print "PSKeyword"
        res += '<keyword>' + obj.name + '</keyword>'
        return res

    if isinstance(obj, PSLiteral):
        #print "PSLiteral"
        res += '<literal>' + obj.name + '</literal>'
        return res

    if isnumber(obj):
        #print "Number " + str(obj)
        res += '<number>' + str(obj) + '</number>'
        return res

    raise TypeError(obj)

# dumptrailers
def dumptrailers(doc):
    #print "dumptrailers"
    res = ""
    for xref in doc.xrefs:
        res += '<trailer>\n'
        #print "before trailerdump"
        res += dumpxml(xref.trailer)
        #print "after trailerdump"
        res += '\n</trailer>\n\n'
    return res

# dumpallobjs
def dumpallobjs(doc, codec=None):
    #print "dumpallobjs"
    res = ""
    visited = set()
    res += '<pdf>'
    for xref in doc.xrefs:
        for objid in xref.get_objids():
            if objid in visited: continue
            visited.add(objid)
            try:
                obj = doc.getobj(objid)
                if obj is None: continue
                res += '<object id="' + str(objid) + '">\n'
                res += dumpxml(obj, codec=codec)
                #print "after obj dump"
                res += '\n</object>\n\n'
            except PDFObjectNotFound, e:
                #print >>sys.stderr, 'not found: %r' % e
		pass
    #print "before dumptrailers"
    res += dumptrailers(doc)
    #print "after dumptrailers"
    res += '</pdf>'
    return res

# extractembedded
LITERAL_FILESPEC = LIT('Filespec')
LITERAL_EMBEDDEDFILE = LIT('EmbeddedFile')
def extractembedded(outfp, fname, objids, pagenos, password='',
                    dumpall=False, codec=None, extractdir=None):
    def extract1(obj):
        filename = os.path.basename(obj['UF'] or obj['F'])
        fileref = obj['EF']['F']
        fileobj = doc.getobj(fileref.objid)
        if not isinstance(fileobj, PDFStream):
            raise PDFValueError(
                'unable to process PDF: reference for %r is not a PDFStream' %
                (filename))
        if fileobj.get('Type') is not LITERAL_EMBEDDEDFILE:
            raise PDFValueError(
                'unable to process PDF: reference for %r is not an EmbeddedFile' %
                (filename))
        path = os.path.join(extractdir, filename)
        if os.path.exists(path):
            raise IOError('file exists: %r' % path)
        print >>sys.stderr, 'extracting: %r' % path
        out = file(path, 'wb')
        out.write(fileobj.get_data())
        out.close()
        return

    fp = file(fname, 'rb')
    parser = PDFParser(fp)
    doc = PDFDocument(parser, password)
    for xref in doc.xrefs:
        for objid in xref.get_objids():
            obj = doc.getobj(objid)
            if isinstance(obj, dict) and obj.get('Type') is LITERAL_FILESPEC:
                extract1(obj)
    return

# dumppdf
def dumppdf(fname, objids, pagenos, password='',
            dumpall=False, codec=None, extractdir=None):
    fp = file(fname, 'rb')
    parser = PDFParser(fp)
    doc = PDFDocument(parser, password)
    res = ""
    if objids:
        for objid in objids:
            obj = doc.getobj(objid)
            res += dumpxml(obj, codec=codec)
    if pagenos:
        for (pageno,page) in enumerate(PDFPage.create_pages(doc)):
            if pageno in pagenos:
                if codec:
                    for obj in page.contents:
                        obj = stream_value(obj)
                        res += dumpxml( obj, codec=codec)
                else:
                    res += dumpxml(page.attrs)
    #print "before dumpall"
    if dumpall:
        res += dumpallobjs( doc, codec=codec)
        #print "after dumpall"
    if (not objids) and (not pagenos) and (not dumpall):
        res += dumptrailers( doc)
    fp.close()
    if codec not in ('raw','binary'):
        res += '\n'
    #print "end proc"
    return res


# main
def main(fname):
    """import getopt
    def usage():
        print 'usage: %s [-d] [-a] [-p pageid] [-P password] [-r|-b|-t] [-T] [-E directory] [-i objid] file ...' % argv[0]
        return 100
    try:
        (opts, args) = getopt.getopt(argv[1:], 'dap:P:rbtTE:i:')
    except getopt.GetoptError:
        return usage()
    if not args: return usage()"""
    debug = 0
    objids = []
    pagenos = set()
    codec = None
    password = ''
    dumpall = False
    proc = dumppdf
    outfp = sys.stdout
    extractdir = None
    """for (k, v) in opts:
        if k == '-d': debug += 1
        elif k == '-o': outfp = file(v, 'wb')
        elif k == '-i': objids.extend( int(x) for x in v.split(',') )
        elif k == '-p': pagenos.update( int(x)-1 for x in v.split(',') )
        elif k == '-P': password = v"""
    dumpall = True
    """elif k == '-r': codec = 'raw'
        elif k == '-b': codec = 'binary'"""
    codec = 'text'
    """elif k == '-T': proc = dumpoutline
        elif k == '-E':
            extractdir = v
            proc = extractembedded"""
    #
    PDFDocument.debug = debug
    PDFParser.debug = debug
    #
    #for fname in args:
    #print fname
    res = ""
    try:
        res += proc(fname, objids, pagenos, password=password,
             dumpall=dumpall, codec=codec, extractdir=extractdir)
    except Exception as e:
        print e
    #print "about to return"
    return res
    

if __name__ == '__main__': sys.exit(main(sys.argv))
