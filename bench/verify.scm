;; Layout verification: apply a fixed sequence of edits, then dump the bounding rectangle
;; of every child of the document body (and the cursor path) to TMVERIFY_OUT.
;; Run with the stock and the patched TeXmacs; the dumps must be identical.
(define verify-out (getenv "TMVERIFY_OUT"))

(define (verify-body) (buffer-get-body (current-buffer)))
(define (verify-first-par)
  (let loop ((i 0))
    (let ((body (verify-body)))
      (if (>= i (tree-arity body)) #f
          (let ((t (tree-ref body i)))
            (if (or (and (tree-atomic? t) (> (string-length (tree->string t)) 20))
                    (tree-is? t 'concat))
                t (loop (+ i 1))))))))

(define (verify-type s)
  (for-each (lambda (c) (key-press (if (== c #\space) "space" (string c)))) (string->list s)))

(define verify-steps
  (list
    (lambda () (let ((t (verify-first-par))) (if t (tree-go-to t :end))))
    (lambda () (verify-type "abcd efgh ijkl mnop qrst uvwx yzab cdef ghij klmn opqr stuv wxyz "))
    (lambda () (key-press "return"))
    (lambda () (verify-type "nuovo paragrafo in cima "))
    (lambda () (make-section 'section) (verify-type "Titolo nuovo"))
    (lambda () (key-press "return") (verify-type "testo dopo la sezione "))
    (lambda () (key-press "$") (verify-type "x+y=z") (key-press "$"))
    (lambda () (let* ((b (verify-body)) (t (tree-ref b (quotient (tree-arity b) 2))))
                 (tree-go-to t :end)))
    (lambda () (verify-type " testo a meta documento "))
    (lambda () (key-press "backspace") (key-press "backspace") (key-press "backspace"))
    (lambda () (let ((t (verify-first-par))) (if t (tree-go-to t :start))))
    (lambda () (key-press "delete") (key-press "delete"))
    ;; join two paragraphs at two thirds of the document (paragraph removal)
    (lambda () (let* ((b (verify-body)) (t (tree-ref b (quotient (* 2 (tree-arity b)) 3))))
                 (tree-go-to t :start) (key-press "backspace")))
    ;; several new paragraphs further down, then undo one step
    (lambda () (let* ((b (verify-body)) (t (tree-ref b (quotient (tree-arity b) 3))))
                 (tree-go-to t :end)
                 (key-press "return") (verify-type "uno ")
                 (key-press "return") (verify-type "due ")))
    (lambda () (undo 0))
    (lambda () (go-end) (verify-type " fine "))))

(define (verify-dump)
  (call-with-output-file verify-out
    (lambda (port)
      (let* ((body (buffer-get-body (current-buffer))) (n (tree-arity body)))
        (format port "buffer ~a arity ~a buffer-tree-arity ~a cursor ~a~%"
                (url->system (current-buffer)) n (tree-arity (buffer-tree)) (cursor-path))
        (do ((i 0 (+ i 1))) ((= i n))
          (format port "~a ~a ~a~%" i (tree-label (tree-ref body i))
                  (tree-bounding-rectangle (tree-ref body i))))))))

;; TMVERIFY_READY set (pixel mode, see verify-pixels.py): after the edits, go to the start,
;; signal readiness and wait until the external driver (which pages through the document and
;; takes screenshots) creates TMVERIFY_DONE.
(define verify-ready (getenv "TMVERIFY_READY"))
(define verify-done (getenv "TMVERIFY_DONE"))
(define (verify-wait-done)
  (if (url-exists? verify-done)
      (begin (buffer-pretend-saved (current-buffer)) (quit-TeXmacs) #t)
      200))
(define (verify-finish)
  (verify-dump)
  (if verify-ready
      (begin (with f (getenv "TMVERIFY_START")   ; fraction of the body, default: start
               (if f
                   (let* ((b (verify-body))
                          (i (inexact->exact (floor (* (string->number f) (tree-arity b))))))
                     (tree-go-to (tree-ref b (min i (- (tree-arity b) 1))) :start))
                   (go-start)))
             (call-with-output-file verify-ready (lambda (port) (display "ready" port)))
             (delayed (:pause 200) (exec-delayed-pause verify-wait-done)))
      (begin (buffer-pretend-saved (current-buffer)) (quit-TeXmacs))))

(define verify-rest (if (getenv "TMVERIFY_NOEDIT") (list) verify-steps))
(define (verify-step)
  (if (null? verify-rest)
      (begin (verify-finish) #t)
      (begin ((car verify-rest)) (set! verify-rest (cdr verify-rest)) 400)))

(delayed (:pause 3000) (exec-delayed-pause verify-step))
