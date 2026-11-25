import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

try:
    import numpy as np
    import onnx
    import onnxruntime
except ImportError:
    onnx=None

from xunyuan_eval.io import FormatError
from xunyuan_eval.onnx_runtime_v2 import (POLICY_INPUTS,POLICY_OUTPUTS,READER_INPUTS,READER_OUTPUTS,
    ModelTimeout,check_submission,model_session,package_models,timed_inference,run_submission,initial_memory)


@unittest.skipIf(onnx is None,'需要 ONNX 和 ONNX Runtime')
class OnnxV2Tests(unittest.TestCase):
    def setUp(self):
        from tools.make_v2_interface_example import export
        self.export=export
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        export(self.root/'policy.onnx',POLICY_INPUTS,POLICY_OUTPUTS,{})
        export(self.root/'reader.onnx',READER_INPUTS,READER_OUTPUTS,{})
        (self.root/'report.pdf').write_bytes(b'%PDF-1.4\n%%EOF\n')
        self.manifest={'schema_version':'2.0','team':'test','policy':'policy.onnx','reader':'reader.onnx','report':'report.pdf'}
        self.submission=self.root/'submission.json';self.save_manifest()

    def save_manifest(self):
        self.submission.write_text(json.dumps(self.manifest))

    def test_stateless_model_can_skip_optional_sensors(self):
        inputs={k:v for k,v in POLICY_INPUTS.items() if k in {'front_rgb','instructions'}}
        outputs={'action':POLICY_OUTPUTS['action']}
        self.export(self.root/'stateless.onnx',inputs,outputs,{})
        session=model_session(self.root/'stateless.onnx',POLICY_INPUTS,POLICY_OUTPUTS)
        values=timed_inference(session,['action'],{'front_rgb':np.zeros((1,3,144,256),np.float32),'instructions':np.ones((1,11),np.int64)})
        self.assertEqual(values[0].shape,(1,16))

    def test_memory_size_can_hold_history_for_a_pretrained_controller(self):
        inputs=dict(POLICY_INPUTS);outputs=dict(POLICY_OUTPUTS)
        inputs['memory']=('tensor(float)',[1,265]);outputs['memory_out']=('tensor(float)',[1,265])
        self.export(self.root/'history.onnx',inputs,outputs,{})
        session=model_session(self.root/'history.onnx',POLICY_INPUTS,POLICY_OUTPUTS)
        self.assertEqual(initial_memory(session).shape,(1,265))

    def test_missing_camera_is_rejected(self):
        inputs={k:v for k,v in POLICY_INPUTS.items() if k!='front_rgb'}
        self.export(self.root/'bad.onnx',inputs,POLICY_OUTPUTS,{})
        with self.assertRaises(FormatError):model_session(self.root/'bad.onnx',POLICY_INPUTS,POLICY_OUTPUTS)

    def test_wrong_image_dimensions_are_rejected(self):
        inputs=dict(POLICY_INPUTS);inputs['front_rgb']=('tensor(float)',[1,3,100,100])
        self.export(self.root/'bad.onnx',inputs,POLICY_OUTPUTS,{})
        with self.assertRaises(FormatError):model_session(self.root/'bad.onnx',POLICY_INPUTS,POLICY_OUTPUTS)

    def test_external_weights_must_be_bundled_into_onnx(self):
        model=onnx.load(str(self.root/'policy.onnx'))
        tensor=model.graph.node[0].attribute[0].t
        tensor.ClearField('raw_data');tensor.data_location=onnx.TensorProto.EXTERNAL
        entry=tensor.external_data.add();entry.key='location';entry.value='../weights.bin'
        (self.root/'bad.onnx').write_bytes(model.SerializeToString())
        with self.assertRaisesRegex(FormatError,'一个 ONNX'):
            model_session(self.root/'bad.onnx',POLICY_INPUTS,POLICY_OUTPUTS)

    def test_report_file_is_checked(self):
        (self.root/'report.pdf').write_text('wrong file')
        with self.assertRaisesRegex(FormatError,'PDF'):check_submission(self.submission)

    def test_model_package_can_be_extracted_and_checked(self):
        result=package_models(self.submission,self.root/'package.zip')
        self.assertEqual(len(result['sha256']),64)
        with zipfile.ZipFile(self.root/'package.zip') as archive:
            self.assertEqual(set(archive.namelist()),{'submission.json','policy.onnx','reader.onnx','report.pdf'})
            archive.extractall(self.root/'extracted')
        data,files,_,_=check_submission(self.root/'extracted/submission.json')
        self.assertEqual(data['team'],'test');self.assertEqual(len(files),3)

    def test_modified_package_file_fails_checksum(self):
        package_models(self.submission,self.root/'package.zip')
        with zipfile.ZipFile(self.root/'package.zip') as archive:archive.extractall(self.root/'extracted')
        (self.root/'extracted/report.pdf').write_bytes(b'%PDF-1.4\nchanged\n')
        with self.assertRaisesRegex(FormatError,'校验值'):
            check_submission(self.root/'extracted/submission.json')

    def test_video_input_error_is_reported_before_running_simulation(self):
        (self.root/'bad_video_reference.json').write_text('{"events":[]}')
        output=self.root/'results'
        with self.assertRaises(FormatError):
            run_submission(self.submission,Path(__file__).resolve().parents[1]/'challenges/v2',output,
                           videos=self.root/'videos',video_reference=self.root/'bad_video_reference.json')
        self.assertFalse(output.exists())

    def test_timeout_sets_runtime_cancellation_flag(self):
        class WaitingSession:
            def run(self,outputs,feed,run_options):
                while not run_options.terminate:time.sleep(.001)
                raise RuntimeError('terminated')
        started=time.monotonic()
        with self.assertRaises(ModelTimeout):timed_inference(WaitingSession(),[],{},timeout_s=.01)
        self.assertLess(time.monotonic()-started,.5)


if __name__=='__main__':unittest.main()
