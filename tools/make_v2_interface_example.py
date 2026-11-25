"""Create neutral-action ONNX files for checking the submission interface."""
from pathlib import Path
import argparse
import json
import numpy as np
import onnx
from onnx import TensorProto,helper,numpy_helper
from xunyuan_eval.onnx_runtime_v2 import POLICY_INPUTS,POLICY_OUTPUTS,READER_INPUTS,READER_OUTPUTS


def export(path,inputs,outputs,values):
    kinds={'tensor(float)':TensorProto.FLOAT,'tensor(int64)':TensorProto.INT64,'tensor(bool)':TensorProto.BOOL}
    ins=[helper.make_tensor_value_info(name,kinds[kind],shape) for name,(kind,shape) in inputs.items()]
    outs=[helper.make_tensor_value_info(name,kinds[kind],shape) for name,(kind,shape) in outputs.items()]
    nodes=[]
    for name,(kind,shape) in outputs.items():
        if name=='memory_out':nodes.append(helper.make_node('Identity',['memory'],[name]));continue
        dtype={'tensor(float)':np.float32,'tensor(int64)':np.int64,'tensor(bool)':np.bool_}[kind]
        array=np.full(shape,values.get(name,0),dtype=dtype)
        nodes.append(helper.make_node('Constant',[],[name],value=numpy_helper.from_array(array)))
    model=helper.make_model(helper.make_graph(nodes,'interface_example',ins,outs),opset_imports=[helper.make_opsetid('',17)])
    model.ir_version=9;onnx.checker.check_model(model);onnx.save(model,str(path))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    export(a.output/'policy.onnx',POLICY_INPUTS,POLICY_OUTPUTS,{})
    export(a.output/'reader.onnx',READER_INPUTS,READER_OUTPUTS,{})
    # A small valid PDF for the interface example.
    stream=b'BT /F1 16 Tf 60 730 Td (ONNX interface example) Tj ET'
    objects=[b'<</Type/Catalog/Pages 2 0 R>>',b'<</Type/Pages/Kids[3 0 R]/Count 1>>',
             b'<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>',
             b'<</Length '+str(len(stream)).encode()+b'>>stream\n'+stream+b'\nendstream',
             b'<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>']
    pdf=bytearray(b'%PDF-1.4\n');offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(pdf));pdf.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref=len(pdf);pdf.extend(b'xref\n0 6\n0000000000 65535 f \n')
    for offset in offsets[1:]:pdf.extend(f'{offset:010d} 00000 n \n'.encode())
    pdf.extend(f'trailer<</Size 6/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n'.encode())
    (a.output/'report.pdf').write_bytes(pdf)
    (a.output/'submission.json').write_text(json.dumps({'schema_version':'2.0','team':'interface-example','policy':'policy.onnx','reader':'reader.onnx','report':'report.pdf'},indent=2)+'\n')
    print(a.output/'submission.json')
