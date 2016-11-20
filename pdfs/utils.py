from io import BytesIO
from PyPDF2 import PdfFileMerger


def concat_pdf(*infiles, **kwargs):
    if 'outfile' in kwargs:
        outfile = kwargs['outfile']
    else:
        outfile = None

# def concat_pdf(*infiles, outfile=None):
# replace above with this once we move to py3 (see pep3102)

    if outfile is None:
        outfile = BytesIO()
    m = PdfFileMerger()

    for f in infiles:
        m.append(f)

    m.write(outfile)
    outfile.flush()
    return outfile
