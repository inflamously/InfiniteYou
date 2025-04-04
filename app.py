# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates. All rights reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import os
import sys
import gradio as gr
import pillow_avif
import torch
from pillow_heif import register_heif_opener

from pipelines.pipeline_infu_flux import InfUFluxPipeline

parser = argparse.ArgumentParser()
parser.add_argument('--base_model_path', default='black-forest-labs/FLUX.1-dev')
parser.add_argument('--clip_encoder_path', default=None)
args = parser.parse_args()

# Register HEIF support for Pillow
register_heif_opener()

class ModelVersion:
    STAGE_1 = "sim_stage1"
    STAGE_2 = "aes_stage2"

    DEFAULT_VERSION = STAGE_2
    
ENABLE_ANTI_BLUR_DEFAULT = False
ENABLE_REALISM_DEFAULT = False

pipeline = None
loaded_pipeline_config = {
    "model_version": "aes_stage2",
    "enable_realism": False,
    "enable_anti_blur": False,
}

def prepare_pipeline(model_version, enable_realism, enable_anti_blur):
    global pipeline

    if (
        pipeline 
        and loaded_pipeline_config["enable_realism"] == enable_realism 
        and loaded_pipeline_config["enable_anti_blur"] == enable_anti_blur
        and model_version == loaded_pipeline_config["model_version"]
    ):
        return
    
    loaded_pipeline_config["enable_realism"] = enable_realism
    loaded_pipeline_config["enable_anti_blur"] = enable_anti_blur
    loaded_pipeline_config["model_version"] = model_version

    if pipeline is None or pipeline.model_version != model_version:
        del pipeline

        model_path = f'./models/InfiniteYou/infu_flux_v1.0/{model_version}'
        print(f'loading model from {model_path}')
        print(f'loading flux model from {args.base_model_path}')

        pipeline = InfUFluxPipeline(
            base_model_path=args.base_model_path,
            infu_model_path=model_path,
            insightface_root_path='./models/InfiniteYou/supports/insightface',
            image_proj_num_tokens=8,
            infu_flux_version='v1.0',
            model_version=model_version,
        )

    pipeline.pipe.delete_adapters(['realism', 'anti_blur'])
    loras = []
    if enable_realism:
        loras.append(['./models/InfiniteYou/supports/optional_loras/flux_realism_lora.safetensors', 'realism', 1.0])
    if enable_anti_blur:
        loras.append(['./models/InfiniteYou/supports/optional_loras/flux_anti_blur_lora.safetensors', 'anti_blur', 1.0])
    pipeline.load_loras(loras)


def generate_image(
    input_image, 
    control_image, 
    prompt, 
    seed, 
    width,
    height,
    guidance_scale, 
    num_steps, 
    infusenet_conditioning_scale, 
    infusenet_guidance_start,
    infusenet_guidance_end,
    enable_realism,
    enable_anti_blur,
    model_version
):
    global pipeline

    prepare_pipeline(model_version=model_version, enable_realism=enable_realism, enable_anti_blur=enable_anti_blur)

    if seed == 0:
        seed = torch.seed() & 0xFFFFFFFF

    try:
        image = pipeline(
            id_image=input_image,
            prompt=prompt,
            control_image=control_image,
            seed=seed,
            width=width,
            height=height,
            guidance_scale=guidance_scale,
            num_steps=num_steps,
            infusenet_conditioning_scale=infusenet_conditioning_scale,
            infusenet_guidance_start=infusenet_guidance_start,
            infusenet_guidance_end=infusenet_guidance_end,
        )
    except Exception as e:
        print(e)
        gr.Error(f"An error occurred: {e}")
        return gr.update()

    return gr.update(value = image, label=f"Generated image, seed = {seed}")


def generate_examples(id_image, control_image, prompt_text, seed, enable_realism, enable_anti_blur, model_version):
    return generate_image(id_image, control_image, prompt_text, seed, 864, 1152, 3.5, 30, 1.0, 0.0, 1.0, enable_realism, enable_anti_blur, model_version)

with gr.Blocks() as demo:
    session_state = gr.State({})
    default_model_version = "v1.0"

    gr.Markdown("""
    <div style="text-align: center; max-width: 900px; margin: 0 auto;">
        <h1 style="font-size: 1.5rem; font-weight: 700; display: block;">InfiniteYou-FLUX</h1>
        <h2 style="font-size: 1.2rem; font-weight: 300; margin-bottom: 1rem; display: block;">Official Gradio Demo for <a href="https://arxiv.org/abs/2503.xxxxx">InfiniteYou: Flexible Photo Recrafting While Preserving Your Identity</a></h2>
        <a href="https://bytedance.github.io/InfiniteYou">[Project Page]</a>&ensp;
        <a href="https://arxiv.org/abs/2503.xxxxx">[Paper]</a>&ensp;
        <a href="https://github.com/bytedance/InfiniteYou">[Code]</a>&ensp;
        <a href="https://huggingface.co/ByteDance/InfiniteYou">[Model]</a>
    </div>

    ### 💡 How to Use This Demo:
    1. **Upload an identity (ID) image containing a human face.** For images with multiple faces, only the largest face will be detected. The face should ideally be clear and large enough, without significant occlusions or blur.
    2. **Enter the text prompt to describe the generated image and select the model version.** Please refer to **important usage tips** under the Generated Image field.
    3. *[Optional] Upload a control image containing a human face.* Only five facial keypoints will be extracted to control the generation. If not provided, we use a black control image, indicating no control.
    4. *[Optional] Adjust advanced hyperparameters or apply optional LoRAs to meet personal needs.* Please refer to **important usage tips** under the Generated Image field.
    5. **Click the "Generate" button to generate an image.** Enjoy!
    """)
    
    with gr.Row():
        with gr.Column(scale=3):
            with gr.Row():
                ui_id_image = gr.Image(label="Identity Image", type="pil", scale=3, height=370, min_width=100)

                with gr.Column(scale=2, min_width=100):
                    ui_control_image = gr.Image(label="Control Image [Optional]", type="pil", height=370, min_width=100)
            
            ui_prompt_text = gr.Textbox(label="Prompt", value="Portrait, 4K, high quality, cinematic")
            ui_model_version = gr.Dropdown(
                label="Model Version",
                choices=[ModelVersion.STAGE_1, ModelVersion.STAGE_2],
                value=ModelVersion.DEFAULT_VERSION,
            )

            ui_btn_generate = gr.Button("Generate")
            with gr.Accordion("Advanced", open=False):
                with gr.Row():
                    ui_num_steps = gr.Number(label="num steps", value=30)
                    ui_seed = gr.Number(label="seed (0 for random)", value=0)
                with gr.Row():
                    ui_width = gr.Number(label="width", value=864)
                    ui_height = gr.Number(label="height", value=1152)
                ui_guidance_scale = gr.Number(label="guidance scale", value=3.5, step=0.5)
                ui_infusenet_conditioning_scale = gr.Slider(minimum=0.0, maximum=1.0, value=1.0, step=0.05, label="infusenet conditioning scale")
                with gr.Row():
                    ui_infusenet_guidance_start = gr.Slider(minimum=0.0, maximum=1.0, value=0.0, step=0.05, label="infusenet guidance start")
                    ui_infusenet_guidance_end = gr.Slider(minimum=0.0, maximum=1.0, value=1.0, step=0.05, label="infusenet guidance end")

            with gr.Accordion("LoRAs [Optional]", open=True):
                with gr.Row():
                    ui_enable_realism = gr.Checkbox(label="Enable realism LoRA", value=ENABLE_REALISM_DEFAULT)
                    ui_enable_anti_blur = gr.Checkbox(label="Enable anti-blur LoRA", value=ENABLE_ANTI_BLUR_DEFAULT)

        with gr.Column(scale=2):
            image_output = gr.Image(label="Generated Image", interactive=False, height=550, format='png')
            gr.Markdown(
                """
                ### ❗️ Important Usage Tips:
                - **Model Version**: `aes_stage2` is used by default for better text-image alignment and aesthetics. For higher ID similarity, please try `sim_stage1`.
                - **Useful Hyperparameters**: Usually, there is NO need to adjust too much. If necessary, try a slightly larger `--infusenet_guidance_start` (*e.g.*, `0.1`) only (especially helpful for `sim_stage1`). If still not satisfactory, then try a slightly smaller `--infusenet_conditioning_scale` (*e.g.*, `0.9`).
                - **Optional LoRAs**: `realism` and `anti-blur`. To enable them, please check the corresponding boxes. They are optional and were NOT used in our paper.
                - **Gender Prompt**: If the generated gender is not preferred, add specific words in the text prompt, such as 'a man', 'a woman', *etc*. We encourage using inclusive and respectful language.
                """
            )

    ui_btn_generate.click(
        generate_image, 
        inputs=[
            ui_id_image, 
            ui_control_image, 
            ui_prompt_text, 
            ui_seed, 
            ui_width,
            ui_height,
            ui_guidance_scale, 
            ui_num_steps, 
            ui_infusenet_conditioning_scale, 
            ui_infusenet_guidance_start, 
            ui_infusenet_guidance_end,
            ui_enable_realism,
            ui_enable_anti_blur,
            ui_model_version
        ], 
        outputs=[image_output], 
        concurrency_id="gpu"
    )

    with gr.Accordion("Local Gradio Demo for Developers", open=False):
        gr.Markdown(
            'Please refer to our GitHub repository to [run the InfiniteYou-FLUX gradio demo locally](https://github.com/bytedance/InfiniteYou#local-gradio-demo).'
        )
    
    gr.Markdown(
        """
        ---
        ### 📜 Disclaimer and Licenses 
        Some images in this demo are from public domains or generated by models. These pictures are intended solely to show the capabilities of our research. If you have any concerns, please contact us, and we will promptly remove any inappropriate content.
        
        The use of the released code, model, and demo must strictly adhere to the respective licenses. Our code is released under the Apache 2.0 License, and our model is released under the Creative Commons Attribution-NonCommercial 4.0 International Public License for academic research purposes only. Any manual or automatic downloading of the face models from [InsightFace](https://github.com/deepinsight/insightface), the [FLUX.1-dev](https://huggingface.co/black-forest-labs/FLUX.1-dev) base model, LoRAs, etc., must follow their original licenses and be used only for academic research purposes.

        This research aims to positively impact the Generative AI field. Users are granted freedom to create images using this tool, but they must comply with local laws and use it responsibly. The developers do not assume any responsibility for potential misuse.
        
        ### 📖 Citation

        If you find InfiniteYou useful for your research or applications, please cite our paper:

        ```bibtex
        @article{jiang2025infiniteyou,
          title={{InfiniteYou}: Flexible Photo Recrafting While Preserving Your Identity},
          author={Jiang, Liming and Yan, Qing and Jia, Yumin and Liu, Zichuan and Kang, Hao and Lu, Xin},
          journal={arXiv preprint},
          volume={arXiv:2503.xxxxx},
          year={2025}
        }
        ```

        We also appreciate it if you could give a star ⭐ to our [Github repository](https://github.com/bytedance/InfiniteYou). Thanks a lot!
        """
    )

prepare_pipeline(model_version=ModelVersion.DEFAULT_VERSION, enable_realism=ENABLE_REALISM_DEFAULT, enable_anti_blur=ENABLE_ANTI_BLUR_DEFAULT)

demo.queue()
demo.launch(server_name='127.0.0.1')  # IPv4
# demo.launch(server_name='[::]')  # IPv6
