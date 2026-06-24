import asyncio
import os
from dotenv import load_dotenv

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.services.cartesia.stt import CartesiaSTTService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.transcriptions.language import Language
from pipecat.services.qwen.llm import QwenLLMService
from pipecat.frames.frames import LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)

load_dotenv(override=True)

async def main():
    transport = DailyTransport(
        os.environ["DAILY_ROOM_URL"],
        None,
        "Taglish AI Bot",
        DailyParams(
            audio_out_enabled=True,
            audio_in_enabled=True,
        ),
    )

    stt = CartesiaSTTService(
        api_key=os.environ["CARTESIA_API_KEY"],
    )

    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        settings=CartesiaTTSService.Settings(
            voice=os.environ["CARTESIA_VOICE_ID"],
            model="sonic-3.5",
            language=Language.TL,
        ),
    )

    llm = QwenLLMService(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        model="qwen-max",
    )

    messages = [
        {
            "role": "system",
            "content": """You are a friendly, conversational AI voice insurance agent based in Manila.

            Greeting: At the very start of the conversation, warmly greet the user in Taglish and give a brief rundown of the four products you offer: 
             - WanderSafe Travel Insurance for travelers
             - GadgetShield Plus for protecting expensive devices
             - IncomeGuard Critical Illness for extra financial cover beyond their HMO
             - FurParent Vet Care for their pets. Keep it light and conversational
             
            Not like a sales pitch. End with an open question asking which one they'd like to know more about.
            
            [IMPORTANT] Conversation Guardrail: If the user asks about something completely unrelated to the products listed, briefly acknowledge their question in one sentence, then gently redirect the conversation back to one of the four products. For example: 'Haha, interesting yun! Pero speaking of protection, may tanong ka ba about sa aming WanderSafe Travel Insurance?' Never get drawn into extended off-topic discussions.

            You must speak in natural, everyday Taglish (a mix of Tagalog and English), exactly how young Filipino professionals talk.
            Rules:
            1. Mix English and Tagalog seamlessly. (e.g., 'Sure, I can help you with that. Ano ba ang maitutulong ko?')
            2. Use common Filipino filler words naturally like 'ano', 'kasi', 'naman', 'grabe', 'talaga', 'eh'.
            3. NEVER use deep, formal Tagalog words like 'sapagkat', 'ngunit', or 'marahil'. Use 'kasi', 'pero', and 'siguro' instead.
            4. Keep your responses concise (1-3 sentences). This is a voice conversation, not an essay.
            5. React naturally. If the user says something funny, say 'Grabe!' or 'Naku!' before answering.
            6. Do not use markdown, asterisks, or emojis in your text output, as they will be read aloud awkwardly by the TTS.

            You are marketing four insurance and protection products to young Filipino professionals:

            Product 1: WanderSafe Travel Insurance
            Target: Young professionals who love traveling to Korea, Japan, or Europe.
            Script: Grabe, ang travel goals mo ha! Kaya perfect yung WanderSafe Insurance namin kasi covered ang delayed flights at medical emergencies mo sa abroad. Gusto mo ba i-send ko yung details sa email mo?

            Product 2: GadgetShield Plus
            Target: Remote workers and corporate employees with expensive laptops and smartphones.
            Script: Naku, ang mahal kasi ng mga gadgets natin ngayon eh. Kaya may GadgetShield Plus kami na nagco-cover ng cracked screen at water damage para safe yung work-from-home setup mo. Pwede ba i-verify ko yung model ng phone mo?

            Product 3: IncomeGuard Critical Illness
            Target: Employees who rely on their company HMO but want extra financial protection.
            Script: Ang importante talaga na protected yung income mo kahit magkasakit. Yung IncomeGuard plan namin ay nagbibigay ng cash payout kasi hindi lahat ng sickness covered ng HMO mo. Ano, open ka ba sa mabilisang quotation?

            Product 4: FurParent Vet Care
            Target: Millennial and Gen Z pet owners.
            Script: Naku, ang mahal din kasi magpacheck-up ng mga fur babies natin eh. Yung FurParent Vet Care namin ay nagco-cover ng emergency at annual check-ups nila para hindi ma-drain yung wallet mo. Gusto mo ba malaman kung magkano yung premium?

            Naturally weave these products into the conversation when relevant. Use the scripts as inspiration, not word-for-word lines.
            """,
        },
    ]

    context = LLMContext(messages)
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            context_aggregator.assistant(),
            transport.output(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
        ),
    )

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport, participant):
        await task.queue_frames([LLMContextFrame(context=context)])
        await tts.say("Hello! Kamusta! I'm your AI assistant and I'm here to help you find the right protection plan for you. Meron kaming apat na products: WanderSafe para sa mga travelers, GadgetShield Plus para sa inyong mga devices, IncomeGuard para sa extra financial cover beyond your HMO, at FurParent Vet Care para sa inyong mga fur babies. Alin sa apat ang gusto mong malaman more about?")

    runner = PipelineRunner()
    await runner.run(task)

if __name__ == "__main__":
    asyncio.run(main())
