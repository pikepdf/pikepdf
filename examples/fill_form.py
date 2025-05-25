from pikepdf import Pdf
from pikepdf.form import DefaultAppearanceStreamGenerator, Form

with Pdf.open('tests/resources/form.pdf') as pdf:
    form = Form(pdf, DefaultAppearanceStreamGenerator)

    form['Text1'].value = 'Hello World!'
    form['Check Box3'].checked = True
    form['Group4'].options[0].select()

    pdf.save('output.pdf')
