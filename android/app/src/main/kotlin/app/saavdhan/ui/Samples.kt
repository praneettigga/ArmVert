package app.saavdhan.ui

/** Demo messages for the video and the benchmark screen (written by the team, modelled on real patterns). */
object Samples {
    data class Sample(val label: String, val text: String, val sender: String?, val expected: String)

    val all = listOf(
        Sample("Bank KYC", "Dear customer your SBI account will be blocked today. Update KYC immediately: http://sbi-kyc-update.xyz/login", "9876543210", "HIGH"),
        Sample("Electricity", "Dear consumer, your electricity power will be disconnected tonight at 9:30 PM because previous month bill was not updated. Please call electricity officer 9123456780 immediately.", "+91 9123456780", "HIGH"),
        Sample("Challan APK", "Aapka traffic challan ₹2,000 pending hai. RTO Challan.apk download kare turant warna court case hoga", "7019283746", "HIGH"),
        Sample("UPI PIN", "You have received a cashback of ₹2,000 from PhonePe. Enter your UPI PIN to receive the amount.", "8899001122", "HIGH"),
        Sample("Digital arrest", "This is Mumbai Cyber Crime Branch. A parcel in your name with drugs was seized by customs. Arrest warrant issued. Join video call now or you will be placed under digital arrest.", "8800112233", "HIGH"),
        Sample("Hindi KYC", "प्रिय ग्राहक, आपका खाता आज बंद हो जाएगा। तुरंत केवाईसी अपडेट करें", "9812300456", "HIGH"),
        Sample("Task job", "Earn ₹5000 daily from home! Just like YouTube videos. Join our Telegram group bit.ly/earn-daily", "9900887766", "HIGH"),
        Sample("Real OTP", "482913 is your OTP for txn of Rs 2,500 at Amazon. Valid 10 mins. Do not share this OTP with anyone. - HDFC Bank", "AX-HDFCBK-S", "LOW"),
        Sample("Real credit", "Rs.500 credited to your A/c XX1234 by UPI from Rahul on 14-Nov. If not done by you, call the number on your card. -ICICI Bank", "JD-ICICIT-S", "LOW"),
        Sample("Friend", "bhai kal 5 baje milte hai, cricket khelne chalenge?", "9812345678", "LOW"),
    )
}
